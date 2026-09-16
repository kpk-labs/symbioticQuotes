CHAIN_ID = 1  # Ethereum mainnet

SAFE = "0x73af5fcdF830035401e00c322D657982b4a71288"  # kpk curator Safe
ADAPTER = "0x97c0baefcf688a8389108a0893144ae0a1408b3a"  # LiquidLaneAdapter (MigratableEntityProxy)
ADAPTER_IMPL = "0xc41b9c2300E444d7031EBDe8aE24e40C268FaE91"  # verified source lives here
VAULT = "0x8bcd746976885b5832bad07b4921e3f2dd1d3703"
ASSET = "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"  # USDC, 6 decimals
PROTOCOL = "0x1ad7dde8c93f41ca717f8ee74295f9325293a94b"  # counterparty in every signed quote

RPC = "https://ethereum-rpc.publicnode.com"

DISCOUNT_PRECISION = 10**6

SAFE_API = "https://safe-transaction-mainnet.safe.global/api/v1"
RFQ_API = "https://swap.symbiotic.fi/api/v1"

FETCH_TTL_SECONDS = 60

ADAPTER_ABI = [
    {"name": "getTokensToRedeemLength", "inputs": [], "outputs": [{"type": "uint256"}],
     "stateMutability": "view", "type": "function"},
    {"name": "tokensToRedeem", "inputs": [{"type": "uint256"}], "outputs": [{"type": "address"}],
     "stateMutability": "view", "type": "function"},
    {"name": "limit", "inputs": [{"type": "address"}], "outputs": [{"type": "uint256"}],
     "stateMutability": "view", "type": "function"},
    {"name": "minDiscount", "inputs": [{"type": "address"}], "outputs": [{"type": "uint256"}],
     "stateMutability": "view", "type": "function"},
    {"name": "accounts", "inputs": [{"type": "address"}], "outputs": [{"type": "address"}],
     "stateMutability": "view", "type": "function"},
    {"name": "isUsedNonce", "inputs": [{"type": "address"}, {"type": "uint256"}], "outputs": [{"type": "bool"}],
     "stateMutability": "view", "type": "function"},
    {"name": "getMaxAssets", "inputs": [{"type": "address"}], "outputs": [{"type": "uint256"}],
     "stateMutability": "nonpayable", "type": "function"},
    {"name": "vault", "inputs": [], "outputs": [{"type": "address"}],
     "stateMutability": "view", "type": "function"},
]

ACCOUNT_ABI = [
    {"name": "totalAssets", "inputs": [], "outputs": [{"type": "uint256"}],
     "stateMutability": "view", "type": "function"},
]

ERC20_ABI = [
    {"name": "symbol", "inputs": [], "outputs": [{"type": "string"}],
     "stateMutability": "view", "type": "function"},
    {"name": "name", "inputs": [], "outputs": [{"type": "string"}],
     "stateMutability": "view", "type": "function"},
    {"name": "decimals", "inputs": [], "outputs": [{"type": "uint8"}],
     "stateMutability": "view", "type": "function"},
]

# Match case-insensitively against the on-chain symbol (mGLOBAL, mF-ONE, deJAAA, deJTRSY, ...).
LOGOS = {
    "MGLOBAL": "https://assets.coingecko.com/coins/images/102172980/small/mglobal-Cm4yjVTI.png?1776956923",
    "MF-ONE": "https://assets.coingecko.com/coins/images/66975/small/mfone-logo.png?1751307469",
    "JTRSY": "https://assets.coingecko.com/coins/images/70445/small/JTRSY.png?1762078582",
    "JAAA": "https://assets.coingecko.com/coins/images/70446/small/jaaa.png?1762078666",
    "DEJTRSY": "https://assets.coingecko.com/coins/images/102175872/small/Centrifuge_Token_from_SVG_to_PNG.png?1787820266",
    "DEJAAA": "https://assets.coingecko.com/coins/images/102172528/small/deJAAA.png?1773764620",
}
