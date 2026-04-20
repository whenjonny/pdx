"""Order executor — routes and executes trades on both venues."""

from __future__ import annotations

import logging
import time
import uuid

from pdx_arb.config import ArbConfig
from pdx_arb.types import ArbSignal, ArbTrade, LegOrder, OrderStatus, Side, Venue

logger = logging.getLogger(__name__)


class ArbExecutor:
    """Executes arbitrage trades across Polymarket and predictX.

    In production this would connect to actual exchange APIs.
    Currently implements paper trading with realistic friction modeling.
    """

    def __init__(
        self,
        config: ArbConfig,
        pdx_client=None,
        dry_run: bool = True,
    ) -> None:
        self.config = config
        self._pdx_client = pdx_client
        self.dry_run = dry_run
        self._trades: list[ArbTrade] = []
        self._filled_count = 0
        self._failed_count = 0

    def execute(self, signal: ArbSignal) -> ArbTrade:
        """Execute a two-legged arbitrage trade."""
        trade_id = f"arb_{uuid.uuid4().hex[:12]}"

        leg_buy = LegOrder(
            venue=signal.buy_venue,
            market_ref=self._market_ref(signal, signal.buy_venue),
            side=signal.buy_side,
            size_usd=signal.suggested_size_usd,
            limit_price=signal.prices.poly.yes_price
            if signal.buy_venue == Venue.POLYMARKET
            else signal.prices.pdx.yes_price,
        )

        sell_side = Side.SELL_YES if signal.buy_side == Side.BUY_YES else Side.SELL_NO
        leg_sell = LegOrder(
            venue=signal.sell_venue,
            market_ref=self._market_ref(signal, signal.sell_venue),
            side=sell_side,
            size_usd=signal.suggested_size_usd,
            limit_price=signal.prices.pdx.yes_price
            if signal.sell_venue == Venue.PREDICTX
            else signal.prices.poly.yes_price,
        )

        if self.dry_run:
            self._paper_fill(leg_buy)
            self._paper_fill(leg_sell)
        else:
            self._live_fill(leg_buy, signal)
            if leg_buy.status == OrderStatus.FILLED:
                self._live_fill(leg_sell, signal)
            else:
                leg_sell.status = OrderStatus.CANCELLED

        if leg_buy.status == OrderStatus.FILLED and leg_sell.status == OrderStatus.FILLED:
            pnl_gross = (leg_sell.fill_price - leg_buy.fill_price) * leg_buy.fill_size
            pnl_net = pnl_gross - leg_buy.fee_paid - leg_sell.fee_paid
            status = "filled"
            self._filled_count += 1
        else:
            pnl_gross = 0.0
            pnl_net = 0.0
            status = "failed"
            self._failed_count += 1

        trade = ArbTrade(
            trade_id=trade_id,
            signal=signal,
            leg_buy=leg_buy,
            leg_sell=leg_sell,
            status=status,
            pnl_gross=pnl_gross,
            pnl_net=pnl_net,
        )
        self._trades.append(trade)

        logger.info(
            "TRADE %s: %s | buy@%.4f sell@%.4f | gross=$%.2f net=$%.2f",
            trade_id, status,
            leg_buy.fill_price, leg_sell.fill_price,
            pnl_gross, pnl_net,
        )
        return trade

    def _market_ref(self, signal: ArbSignal, venue: Venue) -> str:
        if venue == Venue.POLYMARKET:
            return signal.pair.poly_condition_id
        return str(signal.pair.pdx_market_id)

    def _paper_fill(self, leg: LegOrder) -> None:
        """Simulate a fill with realistic slippage."""
        slippage_pct = self.config.slippage_bps / 10_000
        if leg.side in (Side.BUY_YES, Side.BUY_NO):
            leg.fill_price = leg.limit_price * (1 + slippage_pct)
        else:
            leg.fill_price = leg.limit_price * (1 - slippage_pct)
        leg.fill_size = leg.size_usd / leg.fill_price if leg.fill_price > 0 else 0
        if leg.venue == Venue.POLYMARKET:
            leg.fee_paid = leg.size_usd * self.config.polymarket.fee_bps_taker / 10_000
        else:
            leg.fee_paid = leg.size_usd * self.config.predictx.fee_bps_normal / 10_000
        leg.status = OrderStatus.FILLED
        leg.tx_hash = f"paper_{uuid.uuid4().hex[:8]}"

    def _live_fill(self, leg: LegOrder, signal: ArbSignal) -> None:
        """Execute a real trade on the appropriate venue."""
        if leg.venue == Venue.PREDICTX and self._pdx_client is not None:
            try:
                amount_raw = int(leg.size_usd * 1_000_000)
                if leg.side == Side.BUY_YES:
                    result = self._pdx_client.buy_yes(signal.pair.pdx_market_id, amount_raw)
                elif leg.side == Side.BUY_NO:
                    result = self._pdx_client.buy_no(signal.pair.pdx_market_id, amount_raw)
                elif leg.side == Side.SELL_YES:
                    result = self._pdx_client.sell(
                        signal.pair.pdx_market_id, True, amount_raw,
                    )
                else:
                    result = self._pdx_client.sell(
                        signal.pair.pdx_market_id, False, amount_raw,
                    )
                leg.fill_price = leg.limit_price
                leg.fill_size = result.tokens_amount / 1_000_000
                leg.fee_paid = result.fee / 1_000_000
                leg.tx_hash = result.tx_hash
                leg.status = OrderStatus.FILLED
            except Exception as exc:
                logger.error("predictX execution failed: %s", exc)
                leg.status = OrderStatus.FAILED
        else:
            logger.warning("Live execution for %s not implemented", leg.venue.name)
            leg.status = OrderStatus.FAILED

    @property
    def trades(self) -> list[ArbTrade]:
        return list(self._trades)

    @property
    def open_trades(self) -> list[ArbTrade]:
        return [t for t in self._trades if t.status == "filled" and not t.settled]

    def summary(self) -> dict:
        total_pnl = sum(t.pnl_net for t in self._trades if t.status == "filled")
        total_volume = sum(t.leg_buy.size_usd + t.leg_sell.size_usd for t in self._trades)
        return {
            "total_trades": len(self._trades),
            "filled": self._filled_count,
            "failed": self._failed_count,
            "total_pnl": total_pnl,
            "total_volume": total_volume,
            "open_positions": len(self.open_trades),
        }
