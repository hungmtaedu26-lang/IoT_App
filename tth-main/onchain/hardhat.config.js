require("dotenv").config();
require("@nomicfoundation/hardhat-toolbox");

const {
  ETH_RPC_URL,
  ETH_PRIVATE_KEY,
  ETH_CHAIN_ID,
  ETHERSCAN_API_KEY,
} = process.env;

function parseChainId(defaultId) {
  if (!ETH_CHAIN_ID) {
    return defaultId;
  }
  const parsed = parseInt(ETH_CHAIN_ID, 10);
  return Number.isNaN(parsed) ? defaultId : parsed;
}

/** @type import('hardhat/config').HardhatUserConfig */
module.exports = {
  solidity: "0.8.18",
  networks: {
    hardhat: {
      chainId: 31337,
    },
    sepolia: {
      url: ETH_RPC_URL || "https://sepolia.infura.io/v3/YOUR_KEY",
      accounts: ETH_PRIVATE_KEY ? [ETH_PRIVATE_KEY] : [],
      chainId: parseChainId(11155111),
    },
  },
  etherscan: {
    apiKey: ETHERSCAN_API_KEY || "",
  },
};
