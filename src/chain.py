from web3 import Web3

from .config import ACCOUNT_ABI, ADAPTER, ADAPTER_ABI, ERC20_ABI, RPC

ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"


def get_web3() -> Web3:
    return Web3(Web3.HTTPProvider(RPC))


def get_adapter(w3: Web3):
    return w3.eth.contract(address=Web3.to_checksum_address(ADAPTER), abi=ADAPTER_ABI)


def fetch_roster(w3: Web3, adapter) -> list[str]:
    n = adapter.functions.getTokensToRedeemLength().call()
    return [adapter.functions.tokensToRedeem(i).call() for i in range(n)]


def fetch_token_state(w3: Web3, adapter, token: str) -> dict:
    token = Web3.to_checksum_address(token)

    limit = adapter.functions.limit(token).call()
    floor_ppm = adapter.functions.minDiscount(token).call()
    capacity = adapter.functions.getMaxAssets(token).call()
    account_addr = adapter.functions.accounts(token).call()

    deployed = 0
    if account_addr.lower() != ZERO_ADDRESS:
        account = w3.eth.contract(address=account_addr, abi=ACCOUNT_ABI)
        deployed = account.functions.totalAssets().call()

    symbol, name, decimals = fetch_erc20_meta(w3, token)

    return {
        "address": token,
        "symbol": symbol,
        "name": name,
        "decimals": decimals,
        "limit": limit,
        "floor_ppm": floor_ppm,
        "deployed": deployed,
        "capacity": capacity,
    }


def fetch_erc20_meta(w3: Web3, token: str) -> tuple[str, str, int]:
    token = Web3.to_checksum_address(token)
    erc20 = w3.eth.contract(address=token, abi=ERC20_ABI)
    symbol = erc20.functions.symbol().call()
    name = erc20.functions.name().call()
    decimals = erc20.functions.decimals().call()
    return symbol, name, decimals


def fetch_revocations(w3: Web3, adapter, token_nonce_pairs: set[tuple[str, str]]) -> dict[tuple[str, str], bool]:
    """isUsedNonce for every (token, nonce) a signed quote references.

    True means REVOKED (invalidateNonce was called), not "redeemed" - swap()
    checks this mapping but never sets it.
    """
    result = {}
    for token, nonce in token_nonce_pairs:
        checksum = Web3.to_checksum_address(token)
        result[(token.lower(), nonce)] = adapter.functions.isUsedNonce(checksum, int(nonce)).call()
    return result
