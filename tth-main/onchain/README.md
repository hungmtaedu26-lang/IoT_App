# ProofRegistry On-Chain Deployment

Thư mục này chứa cấu hình Hardhat tối thiểu để triển khai `ProofRegistry.sol` lên mạng Ethereum (testnet hoặc mainnet).

## Chuẩn bị

1. Cài Node.js (>= 18) và npm.
2. Trong thư mục `onchain/`, chạy `npm install` để bootstrap Hardhat và toolbox.
3. Sao chép `.env.example` thành `.env`, điền:
   - `ETH_RPC_URL`: Endpoint RPC (Infura/Alchemy/tự host).
   - `ETH_PRIVATE_KEY`: Private key tài khoản triển khai (đừng commit).
   - `ETH_CHAIN_ID`: ID mạng (11155111 cho Sepolia, 1 cho mainnet...).
   - (Tuỳ chọn) `ETHERSCAN_API_KEY`, `ETH_GAS_PRICE_GWEI`, `ETH_MAX_PRIORITY_FEE_GWEI`.

## Triển khai

```bash
npm run build              # biên dịch contract
npm run deploy:sep         # ví dụ triển khai lên Sepolia (cần RPC + private key)
# hoặc chỉ định mạng khác
npx hardhat run scripts/deploy.js --network <ten-mang>
```

Console sẽ in địa chỉ contract (`ProofRegistry deployed to: ...`). Sao chép địa chỉ đó vào `.env` ở dự án chính (`ETH_CONTRACT_ADDRESS=`) trước khi khởi động listener on-chain.

## Kiểm chứng & xác thực

- Dùng `npx hardhat verify --network <ten-mang> <dia-chi>` nếu muốn verify trên explorer (cần API key tương ứng).
- Kiểm tra giao dịch trên Etherscan hay explorer của mạng.

## Lưu ý

- Private key bắt buộc phải có ETH đủ để trả gas trên mạng bạn chọn.
- Nếu triển khai lên mainnet, xem xét cấu hình gas (`ETH_GAS_PRICE_GWEI`, `ETH_MAX_PRIORITY_FEE_GWEI`) để tránh giao dịch bị pending quá lâu.
- Hardhat cung cấp mạng cục bộ (`npx hardhat node`) để thử nghiệm, nhưng listener chỉ đẩy giao dịch lên khi `.env` chính có RPC thật.
