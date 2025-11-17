const hre = require("hardhat");

async function main() {
  await hre.run("compile");

  const ProofRegistry = await hre.ethers.getContractFactory("ProofRegistry");
  const registry = await ProofRegistry.deploy();
  await registry.waitForDeployment();

  const address = await registry.getAddress();
  console.log("ProofRegistry deployed to:", address);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
