import logging
import time
from web3 import Web3
from eth_account import Account
from app.config import settings
from app.utils.abi_loader import load_abi
from app.models.schemas import MarketResponse, MarketTrade, EvidenceResponse, UserPosition, UserTransaction

logger = logging.getLogger("blockchain")
from app.services import database as db


class BlockchainService:
    def __init__(self):
        self.w3 = Web3(Web3.HTTPProvider(settings.rpc_url))
        self._market_contract = None
        self._usdc_contract = None
        self._oracle_contract = None
        self._account = None

    @property
    def account(self):
        if self._account is None and settings.deployer_private_key:
            self._account = Account.from_key(settings.deployer_private_key)
        return self._account

    @property
    def is_connected(self) -> bool:
        try:
            return self.w3.is_connected()
        except Exception:
            return False

    @property
    def market_contract(self):
        if self._market_contract is None and settings.pdx_market_address:
            abi = load_abi("PDXMarket")
            self._market_contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(settings.pdx_market_address),
                abi=abi,
            )
        return self._market_contract

    @property
    def usdc_contract(self):
        if self._usdc_contract is None and settings.mock_usdc_address:
            abi = load_abi("MockUSDC")
            self._usdc_contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(settings.mock_usdc_address),
                abi=abi,
            )
        return self._usdc_contract

    @property
    def oracle_contract(self):
        if self._oracle_contract is None and settings.pdx_oracle_address:
            abi = load_abi("PDXOracle")
            self._oracle_contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(settings.pdx_oracle_address),
                abi=abi,
            )
        return self._oracle_contract

    def _get_logs(self, event, argument_filters=None):
        """Get event logs with chunked queries to handle RPC block range limits.

        On public/testnet RPCs, querying from block 0 to latest often exceeds
        the provider's max block range (typically 2000-10000 blocks). This
        method queries in chunks to avoid that limit.
        """
        try:
            latest = self.w3.eth.block_number
        except Exception:
            return []

        from_block = settings.deploy_block
        if from_block == 0 and settings.chain_id != 31337:
            # On testnet/mainnet without explicit deploy_block, only scan recent history
            from_block = max(0, latest - 50000)

        # If range is small enough (local anvil, or recent deploy), query directly
        if latest - from_block < 5000:
            try:
                return event.get_logs(
                    argument_filters=argument_filters,
                    fromBlock=from_block,
                    toBlock="latest",
                )
            except Exception as e:
                logger.warning("Direct log query failed: %s", e)
                return []

        # Chunked query for large block ranges
        chunk_size = 5000
        all_logs = []
        current = from_block
        while current <= latest:
            to_block = min(current + chunk_size - 1, latest)
            try:
                logs = event.get_logs(
                    argument_filters=argument_filters,
                    fromBlock=current,
                    toBlock=to_block,
                )
                all_logs.extend(logs)
            except Exception as e:
                logger.warning("Chunked log query failed (%d-%d): %s", current, to_block, e)
            current = to_block + 1

        return all_logs

    def _send_tx(self, func) -> str:
        """Build, sign, and send a contract transaction. Returns tx hash hex."""
        account = self.account
        tx = func.build_transaction({
            "from": account.address,
            "nonce": self.w3.eth.get_transaction_count(account.address),
            "gas": 3_000_000,
            "gasPrice": self.w3.eth.gas_price,
            "chainId": settings.chain_id,
        })
        signed = account.sign_transaction(tx)
        tx_hash = self.w3.eth.send_raw_transaction(signed.rawTransaction)
        self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=30)
        return tx_hash.hex()

    def create_market(self, question: str, deadline_days: int, initial_liquidity_usdc: float) -> dict:
        """Approve USDC, then create a new prediction market."""
        liquidity_raw = int(initial_liquidity_usdc * 1e6)
        deadline = int(time.time()) + deadline_days * 86400

        # Mint USDC to deployer if needed
        balance = self.usdc_contract.functions.balanceOf(self.account.address).call()
        if balance < liquidity_raw:
            mint_amount = liquidity_raw - balance + int(1000 * 1e6)  # extra buffer
            self._send_tx(
                self.usdc_contract.functions.mint(self.account.address, mint_amount)
            )

        # Approve market contract to spend USDC
        self._send_tx(
            self.usdc_contract.functions.approve(
                Web3.to_checksum_address(settings.pdx_market_address),
                2**256 - 1,
            )
        )

        # Create market
        func = self.market_contract.functions.createMarket(
            question,
            b"\x00" * 32,  # no polymarket link
            deadline,
            liquidity_raw,
        )
        tx = func.build_transaction({
            "from": self.account.address,
            "nonce": self.w3.eth.get_transaction_count(self.account.address),
            "gas": 5_000_000,
            "gasPrice": self.w3.eth.gas_price,
            "chainId": settings.chain_id,
        })
        signed = self.account.sign_transaction(tx)
        tx_hash = self.w3.eth.send_raw_transaction(signed.rawTransaction)
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=30)

        # Parse MarketCreated event to get market ID
        logs = self.market_contract.events.MarketCreated().process_receipt(receipt)
        market_id = logs[0]["args"]["marketId"] if logs else self.get_market_count() - 1

        return {
            "market_id": market_id,
            "question": question,
            "deadline": deadline,
            "initial_liquidity": str(liquidity_raw),
            "tx_hash": tx_hash.hex(),
        }

    def mint_usdc(self, to: str, amount_usdc: float) -> dict:
        """Mint MockUSDC to an address."""
        raw = int(amount_usdc * 1e6)
        tx_hash = self._send_tx(
            self.usdc_contract.functions.mint(
                Web3.to_checksum_address(to), raw
            )
        )
        return {"to": to, "amount": str(raw), "tx_hash": tx_hash}

    def settle_market(self, market_id: int, outcome: bool) -> dict:
        """Settle a market via the Oracle contract."""
        if self.oracle_contract:
            tx_hash = self._send_tx(
                self.oracle_contract.functions.settleMarket(market_id, outcome)
            )
        else:
            # Fallback: call settle directly on market (if deployer is oracle)
            tx_hash = self._send_tx(
                self.market_contract.functions.settle(market_id, outcome)
            )
        return {"market_id": market_id, "outcome": outcome, "tx_hash": tx_hash}

    def get_market_count(self) -> int:
        if not self.market_contract:
            return 0
        return self.market_contract.functions.nextMarketId().call()

    def get_market(self, market_id: int) -> MarketResponse | None:
        if not self.market_contract:
            return None
        try:
            m = self.market_contract.functions.markets(market_id).call()
            price_yes = self.market_contract.functions.getPriceYes(market_id).call()
            price_no = self.market_contract.functions.getPriceNo(market_id).call()
            tokens = self.market_contract.functions.getMarketTokens(market_id).call()
            evidence_count = self.market_contract.functions.getEvidenceCount(market_id).call()

            return MarketResponse(
                id=market_id,
                question=m[0],
                reserveYes=m[2],
                reserveNo=m[3],
                k=m[4],
                deadline=m[5],
                lockTime=m[6],
                totalDeposited=m[7],
                feesAccrued=m[8],
                resolved=m[9],
                outcome=m[10],
                creator=m[11],
                yesToken=tokens[0],
                noToken=tokens[1],
                priceYes=price_yes / 1e6,
                priceNo=price_no / 1e6,
                evidenceCount=evidence_count,
                category=self.get_market_category(market_id),
            )
        except Exception:
            return None

    def list_markets(self) -> list[MarketResponse]:
        count = self.get_market_count()
        markets = []
        for i in range(count):
            m = self.get_market(i)
            if m:
                markets.append(m)
        return markets

    def get_evidence_list(self, market_id: int) -> list[EvidenceResponse]:
        if not self.market_contract:
            return []
        try:
            count = self.market_contract.functions.getEvidenceCount(market_id).call()
            evidence = []
            for i in range(count):
                e = self.market_contract.functions.getEvidence(market_id, i).call()
                evidence.append(
                    EvidenceResponse(
                        submitter=e[0],
                        ipfsHash="0x" + e[1].hex(),
                        summary=e[2],
                        timestamp=e[3],
                    )
                )
            return evidence
        except Exception:
            return []

    def set_market_metadata(self, market_id: int, category: str, resolution_source: str) -> None:
        """Store off-chain market metadata (category and resolution source)."""
        db.set_market_metadata(market_id, category, resolution_source)

    def get_market_category(self, market_id: int) -> str:
        """Get stored category for a market, defaulting to 'general'."""
        return db.get_market_category(market_id)

    def get_market_trades(self, market_id: int) -> list[MarketTrade]:
        """Query Trade and Sold events for a specific market."""
        if not self.market_contract:
            return []

        trades: list[MarketTrade] = []

        try:
            trade_logs = self._get_logs(
                self.market_contract.events.Trade,
                argument_filters={"marketId": market_id},
            )
            for log in trade_logs:
                block = self.w3.eth.get_block(log["blockNumber"])
                trade_type = "buy_yes" if log["args"]["isYes"] else "buy_no"
                trades.append(MarketTrade(
                    type=trade_type,
                    trader=log["args"]["trader"],
                    usdc_amount=str(log["args"]["usdcIn"]),
                    token_amount=str(log["args"]["tokensOut"]),
                    fee=str(log["args"]["fee"]),
                    timestamp=block["timestamp"],
                    tx_hash=log["transactionHash"].hex(),
                    block_number=log["blockNumber"],
                ))
        except Exception:
            pass

        try:
            sold_logs = self._get_logs(
                self.market_contract.events.Sold,
                argument_filters={"marketId": market_id},
            )
            for log in sold_logs:
                block = self.w3.eth.get_block(log["blockNumber"])
                sell_type = "sell_yes" if log["args"]["isYes"] else "sell_no"
                trades.append(MarketTrade(
                    type=sell_type,
                    trader=log["args"]["trader"],
                    usdc_amount=str(log["args"]["usdcOut"]),
                    token_amount=str(log["args"]["tokensIn"]),
                    fee="0",
                    timestamp=block["timestamp"],
                    tx_hash=log["transactionHash"].hex(),
                    block_number=log["blockNumber"],
                ))
        except Exception:
            pass

        # Sort by block number descending (most recent first)
        trades.sort(key=lambda t: t.block_number, reverse=True)
        return trades

    def get_token_balance(self, token_address: str, user_address: str) -> int:
        """Read ERC20 balanceOf for a given token and user address."""
        try:
            abi = load_abi("OutcomeToken")
            token_contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(token_address),
                abi=abi,
            )
            return token_contract.functions.balanceOf(
                Web3.to_checksum_address(user_address)
            ).call()
        except Exception:
            return 0

    def get_user_positions(self, address: str) -> list[UserPosition]:
        """Get all markets where user holds YES or NO tokens."""
        markets = self.list_markets()
        positions = []
        checksum_address = Web3.to_checksum_address(address)

        for market in markets:
            try:
                yes_balance = self.get_token_balance(market.yesToken, checksum_address)
                no_balance = self.get_token_balance(market.noToken, checksum_address)

                if yes_balance == 0 and no_balance == 0:
                    continue

                # Estimate current USDC value: balance * price (tokens have 6 decimals like USDC)
                yes_value = yes_balance * market.priceYes
                no_value = no_balance * market.priceNo
                total_value = int(yes_value + no_value)

                positions.append(UserPosition(
                    market_id=market.id,
                    question=market.question,
                    yes_balance=str(yes_balance),
                    no_balance=str(no_balance),
                    current_price_yes=market.priceYes,
                    current_price_no=market.priceNo,
                    market_resolved=market.resolved,
                    market_outcome=market.outcome,
                    current_value_usdc=str(total_value),
                ))
            except Exception:
                continue

        return positions

    def get_user_transactions(self, address: str) -> list[UserTransaction]:
        """Query event logs for all user activity across event types."""
        if not self.market_contract:
            return []

        checksum_address = Web3.to_checksum_address(address)
        transactions = []

        try:
            # Trade events where trader == address
            trade_logs = self._get_logs(
                self.market_contract.events.Trade,
                argument_filters={"trader": checksum_address},
            )
            for log in trade_logs:
                block = self.w3.eth.get_block(log["blockNumber"])
                tx_type = "buy_yes" if log["args"]["isYes"] else "buy_no"
                transactions.append(UserTransaction(
                    type=tx_type,
                    market_id=log["args"]["marketId"],
                    timestamp=block["timestamp"],
                    block_number=log["blockNumber"],
                    tx_hash=log["transactionHash"].hex(),
                    details={
                        "usdc_in": str(log["args"]["usdcIn"]),
                        "tokens_out": str(log["args"]["tokensOut"]),
                        "fee": str(log["args"]["fee"]),
                        "is_yes": log["args"]["isYes"],
                    },
                ))
        except Exception:
            pass

        try:
            # Sold events where trader == address
            sold_logs = self._get_logs(
                self.market_contract.events.Sold,
                argument_filters={"trader": checksum_address},
            )
            for log in sold_logs:
                block = self.w3.eth.get_block(log["blockNumber"])
                transactions.append(UserTransaction(
                    type="sell",
                    market_id=log["args"]["marketId"],
                    timestamp=block["timestamp"],
                    block_number=log["blockNumber"],
                    tx_hash=log["transactionHash"].hex(),
                    details={
                        "is_yes": log["args"]["isYes"],
                        "tokens_in": str(log["args"]["tokensIn"]),
                        "usdc_out": str(log["args"]["usdcOut"]),
                    },
                ))
        except Exception:
            pass

        try:
            # Redeemed events where user == address
            redeemed_logs = self._get_logs(
                self.market_contract.events.Redeemed,
                argument_filters={"user": checksum_address},
            )
            for log in redeemed_logs:
                block = self.w3.eth.get_block(log["blockNumber"])
                transactions.append(UserTransaction(
                    type="redeem",
                    market_id=log["args"]["marketId"],
                    timestamp=block["timestamp"],
                    block_number=log["blockNumber"],
                    tx_hash=log["transactionHash"].hex(),
                    details={
                        "amount": str(log["args"]["amount"]),
                    },
                ))
        except Exception:
            pass

        try:
            # MarketCreated events where creator == address
            created_logs = self._get_logs(
                self.market_contract.events.MarketCreated,
                argument_filters={"creator": checksum_address},
            )
            for log in created_logs:
                block = self.w3.eth.get_block(log["blockNumber"])
                transactions.append(UserTransaction(
                    type="create_market",
                    market_id=log["args"]["marketId"],
                    timestamp=block["timestamp"],
                    block_number=log["blockNumber"],
                    tx_hash=log["transactionHash"].hex(),
                    details={
                        "question": log["args"]["question"],
                        "deadline": log["args"]["deadline"],
                    },
                ))
        except Exception:
            pass

        try:
            # EvidenceSubmitted events where submitter == address
            evidence_logs = self._get_logs(
                self.market_contract.events.EvidenceSubmitted,
                argument_filters={"submitter": checksum_address},
            )
            for log in evidence_logs:
                block = self.w3.eth.get_block(log["blockNumber"])
                transactions.append(UserTransaction(
                    type="submit_evidence",
                    market_id=log["args"]["marketId"],
                    timestamp=block["timestamp"],
                    block_number=log["blockNumber"],
                    tx_hash=log["transactionHash"].hex(),
                    details={
                        "ipfs_hash": "0x" + log["args"]["ipfsHash"].hex(),
                        "summary": log["args"]["summary"],
                    },
                ))
        except Exception:
            pass

        # Sort by block number descending (most recent first)
        transactions.sort(key=lambda t: t.block_number, reverse=True)
        return transactions


blockchain_service = BlockchainService()
