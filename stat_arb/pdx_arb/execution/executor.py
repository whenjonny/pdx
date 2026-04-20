"""Order executor — routes and executes trades on both venues."""

from __future__ import annotations

import logging
import uuid

from pdx_arb.config import ArbConfig
from pdx_arb.types import (
    ArbSignal,
    ArbTrade,
    HedgeAction,
    LegOrder,
    OrderStatus,
    Side,
    Venue,
)

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
        risk_manager=None,
        dry_run: bool = True,
    ) -> None:
        self.config = config
        self._pdx_client = pdx_client
        self._risk = risk_manager
        self.dry_run = dry_run
        self._trades: list[ArbTrade] = []
        self._hedge_actions: list[HedgeAction] = []
        self._filled_count = 0
        self._failed_count = 0

    def execute(
        self,
        signal: ArbSignal,
        cost_per_unit: float = 0.0,
        guaranteed_pnl_per_unit: float = 0.0,
    ) -> ArbTrade | None:
        """Execute a two-legged arbitrage trade.

        Returns None if risk check rejects the signal.
        """
        if self._risk is not None:
            passed, reason = self._risk.check(signal)
            if not passed:
                logger.info("REJECTED: %s — %s", signal.pair.pair_id, reason)
                return None

            if cost_per_unit > 0 and guaranteed_pnl_per_unit > 0:
                sized = self._risk.size_position(
                    cost_per_unit=cost_per_unit,
                    guaranteed_pnl_per_unit=guaranteed_pnl_per_unit,
                    signal=signal,
                )
                if sized < 10.0:
                    logger.debug("Kelly size too small ($%.1f), skip", sized)
                    return None
                signal.suggested_size_usd = sized

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

        sell_side = Side.BUY_NO if signal.buy_side == Side.BUY_YES else Side.BUY_YES
        leg_sell = LegOrder(
            venue=signal.sell_venue,
            market_ref=self._market_ref(signal, signal.sell_venue),
            side=sell_side,
            size_usd=signal.suggested_size_usd,
            limit_price=signal.prices.pdx.no_price
            if signal.sell_venue == Venue.PREDICTX
            else signal.prices.poly.no_price,
        )

        if self.dry_run:
            self._paper_fill(leg_buy)
            self._paper_fill(leg_sell)
        else:
            self._live_fill(leg_buy, signal)
            if self._risk is not None:
                self._risk.record_fill_attempt(
                    signal.pair.pair_id, leg_buy.status == OrderStatus.FILLED,
                )

            if leg_buy.status == OrderStatus.FILLED:
                self._live_fill(leg_sell, signal)
                if self._risk is not None:
                    self._risk.record_fill_attempt(
                        signal.pair.pair_id, leg_sell.status == OrderStatus.FILLED,
                    )
                if leg_sell.status != OrderStatus.FILLED:
                    self._handle_leg_failure(trade_id, leg_buy, leg_sell, signal)
            else:
                leg_sell.status = OrderStatus.CANCELLED

        buy_filled = leg_buy.status == OrderStatus.FILLED
        sell_filled = leg_sell.status == OrderStatus.FILLED

        if buy_filled and sell_filled:
            total_cost = leg_buy.fill_price * leg_buy.fill_size + leg_sell.fill_price * leg_sell.fill_size
            pnl_gross = leg_buy.fill_size - total_cost
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

        if self._risk is not None:
            self._risk.record_trade(trade)

        logger.info(
            "TRADE %s: %s | buy@%.4f sell@%.4f | gross=$%.2f net=$%.2f",
            trade_id, status,
            leg_buy.fill_price, leg_sell.fill_price,
            pnl_gross, pnl_net,
        )
        return trade

    def _handle_leg_failure(
        self,
        trade_id: str,
        filled_leg: LegOrder,
        failed_leg: LegOrder,
        signal: ArbSignal,
    ) -> None:
        """Hedge naked exposure when one leg fails.

        Strategy:
        1. Try to close the filled leg (sell what was just bought)
        2. If that fails, retry the failed leg with wider slippage
        """
        if self._risk is not None:
            self._risk.record_leg_failure(filled_leg.size_usd)

        logger.warning(
            "LEG FAILURE on %s: %s filled, %s failed — attempting hedge",
            trade_id, filled_leg.venue.name, failed_leg.venue.name,
        )

        close_leg = LegOrder(
            venue=filled_leg.venue,
            market_ref=filled_leg.market_ref,
            side=_opposite_side(filled_leg.side),
            size_usd=filled_leg.size_usd,
            limit_price=filled_leg.fill_price,
        )
        self._live_fill(close_leg, signal)

        if close_leg.status == OrderStatus.FILLED:
            close_pnl = (close_leg.fill_price - filled_leg.fill_price) * filled_leg.fill_size
            action = HedgeAction(
                original_trade_id=trade_id,
                failed_venue=failed_leg.venue,
                filled_venue=filled_leg.venue,
                hedge_type="close_filled",
                success=True,
                pnl=close_pnl - close_leg.fee_paid,
            )
            self._hedge_actions.append(action)
            if self._risk is not None:
                self._risk.record_hedge(action)
            filled_leg.status = OrderStatus.CANCELLED
            logger.info("HEDGE OK: closed filled leg, pnl=$%.2f", close_pnl)
            return

        wider_slippage = self.config.hedge_retry_slippage_bps / 10_000
        if failed_leg.side in (Side.BUY_YES, Side.BUY_NO):
            retry_price = failed_leg.limit_price * (1 + wider_slippage)
        else:
            retry_price = failed_leg.limit_price * (1 - wider_slippage)
        retry_leg = LegOrder(
            venue=failed_leg.venue,
            market_ref=failed_leg.market_ref,
            side=failed_leg.side,
            size_usd=failed_leg.size_usd,
            limit_price=retry_price,
        )
        self._live_fill(retry_leg, signal)

        if retry_leg.status == OrderStatus.FILLED:
            failed_leg.status = OrderStatus.FILLED
            failed_leg.fill_price = retry_leg.fill_price
            failed_leg.fill_size = retry_leg.fill_size
            failed_leg.fee_paid = retry_leg.fee_paid
            failed_leg.tx_hash = retry_leg.tx_hash

            action = HedgeAction(
                original_trade_id=trade_id,
                failed_venue=failed_leg.venue,
                filled_venue=filled_leg.venue,
                hedge_type="retry_failed",
                success=True,
                pnl=0.0,
            )
            self._hedge_actions.append(action)
            if self._risk is not None:
                self._risk.record_hedge(action)
            logger.info("HEDGE OK: retried failed leg at wider slippage")
            return

        action = HedgeAction(
            original_trade_id=trade_id,
            failed_venue=failed_leg.venue,
            filled_venue=filled_leg.venue,
            hedge_type="both_failed",
            success=False,
            pnl=-filled_leg.size_usd * wider_slippage,
        )
        self._hedge_actions.append(action)
        if self._risk is not None:
            self._risk.record_hedge(action)
        logger.error("HEDGE FAILED: naked position on %s ($%.0f)", filled_leg.venue.name, filled_leg.size_usd)

    def check_adverse_movement(
        self,
        trade: ArbTrade,
        current_buy_venue_price: float | None = None,
    ) -> None:
        """Check post-trade price movement for adverse selection detection.

        Call this some time after trade execution with the current price on the
        buy venue to detect if the market moved against us (toxic flow signal).

        If *current_buy_venue_price* is not provided, the method uses the
        snapshot price from the original signal (useful for testing only).
        """
        if self._risk is None:
            return

        signal = trade.signal
        entry_price = trade.leg_buy.fill_price

        if current_buy_venue_price is None:
            if signal.buy_venue == Venue.POLYMARKET:
                current_buy_venue_price = signal.prices.poly.yes_price
            else:
                current_buy_venue_price = signal.prices.pdx.yes_price

        if signal.buy_side == Side.BUY_YES:
            adverse = current_buy_venue_price < entry_price
        else:
            adverse = current_buy_venue_price > entry_price

        self._risk.record_price_movement(signal.pair.pair_id, adverse)

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

    @property
    def hedge_actions(self) -> list[HedgeAction]:
        return list(self._hedge_actions)

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
            "hedge_actions": len(self._hedge_actions),
        }


def _opposite_side(side: Side) -> Side:
    return {
        Side.BUY_YES: Side.SELL_YES,
        Side.BUY_NO: Side.SELL_NO,
        Side.SELL_YES: Side.BUY_YES,
        Side.SELL_NO: Side.BUY_NO,
    }[side]
