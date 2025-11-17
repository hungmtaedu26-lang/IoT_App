# Secure Fund Transfer System with Zero-Knowledge Proofs

## Introduction

This project implements a secure fund transfer system using Zero-Knowledge Proofs (specifically zk-SNARKs) that allows:
- Confidential money transfers between users without revealing account balances
- Cryptographic proof generation to validate transfers
- Proof verification through a simulated smart contract
- Storage of transfer proofs on simulated IPFS/Filecoin network

Key Features:
- Complete privacy: Neither the sender's nor receiver's balance is revealed
- Mathematical verification: All transfers are cryptographically proven valid
- Decentralized storage: Proofs are stored on distributed networks
- Web interface: Easy-to-use UI for initiating and receiving transfers

## Setup and Running Instructions

### A Windows Setup (Mock Testing)

1. **Prerequisites**
   ```powershell
   # Make sure you have Python 3.8+ installed
   python --version
   ```

2. **Setup Environment**
   ```powershell
   # Clone and enter the project directory
   cd path/to/project/tth

   # Create and activate virtual environment
    Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypas
   .\scripts\setup_env.ps1
   .\venv\Scripts\Activate.ps1

   # Install dependencies
   pip install -r requirements.txt 
   ```

3. **Run the System**
   ```powershell

   #Install Pysnark
   pip install -e .
   # Start all services
   python scripts\run_all.py
   ```

4. **Using the System**
   - Open `http://localhost:8001/ui` in your browser for Device A (sender)
   - Open `http://localhost:8002/ui` for Device B (receiver)
   - In Device A interface:
     1. Enter the amount to transfer
     2. Click "Submit Transfer"
     3. Wait for proof generation (mock in Windows)
   - Switch to Device B interface to see the updated balance
   - Check `data/` folder for generated mock proofs and transcripts

Note: On Windows, the system uses a mock ZKP backend which simulates the proof generation process.

### B MacOS Setup (Real zk-SNARK Implementation)

1. **Prerequisites**
   ```bash
   # Install Homebrew if not installed
   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

   # Install required system dependencies
   brew install python3 gmp

   # Verify Python installation
   python3 --version
   ```

2. **Setup Environment**
   ```bash
   # Clone and enter the project directory
   cd path/to/project/tth

   # Create and activate virtual environment
   bash scripts/setup_env.sh
   source venv/bin/activate

   # Install dependencies (includes real PySNARK)
   pip install -r requirements.txt
   ```

3. **Run the System**
   ```bash
   # Install pysnark ( if requirements.txt failed)
   pip install -e .

   # Start all services
   python scripts/run_all.py
   ```

4. **Using the System**
   - Open `http://localhost:8001` in your browser for Device A (sender)
   - Open `http://localhost:8002` for Device B (receiver)
   - In Device A interface:
     1. Enter the amount to transfer
     2. Click "Submit Transfer"
     3. Wait for real zk-SNARK proof generation (may take a few seconds)
     4. Observe the proof verification process
   - Switch to Device B interface to verify the received amount
   - Examine generated files:
     - `data/proofs/`: Contains actual zk-SNARK proofs
     - `data/transcripts/`: Verification records
     - `data/ipfs/` & `data/filecoin/`: Simulated storage records

## System Components

When running, the system starts several services:
- Device A (Sender) UI: Web interface for initiating transfers
- Device B (Receiver) UI: Web interface for viewing received transfers
- SNARK Runner: Generates zero-knowledge proofs for transfers
- Smart Contract Listener: Verifies proofs and records transactions
- Storage Services: Simulates storing proofs on IPFS/Filecoin
| -------------------- | ----------------- | ----- |
| Device A FastAPI UI  | `services/device_a` | unchanged REST/UX, now calls SNARK runner |
| Cairo `zkp-runner`   | `services/snark_runner` | swaps Cairo/SHARP for a pluggable SNARK backend (mock by default, PySNARK-ready) |
| Device B FastAPI UI  | `services/device_b` | identical interface for receiver balance |
| Smart-contract daemon | `services/smart_contract/listener.py` | validates proofs and records transcripts locally instead of StarkNet `starkli` invocations |
| IPFS / Filecoin uploaders | `services/storage/ipfs.py`, `services/storage/filecoin.py` | watch proof output folders and simulate pinning/deal submission |

## Project layout

```
zkp_snark_ver/
+- .env.example              # copy to .env to customise ports/flags
+- pyproject.toml
+- requirements.txt
+- scripts/
  +- setup_env.ps1 / setup_env.sh
  +- run_all.py             # convenience launcher for all services
+- services/
  +- device_a/              # sender API + minimal web UI
  +- device_b/              # receiver balance API
  +- snark_runner/          # proof generator and backend plumbing
  +- smart_contract/        # local verifier/transcript writer
  +- storage/               # simulated IPFS & Filecoin daemons
+- shared/                   # common config, models, helpers, proof store
```

Runtime artefacts land underneath `data/` (created on first run):

- `data/proofs/<trace-id>/`  proof, public signals and witness for every transfer
- `data/transcripts/`  verification transcripts emitted by the smart-contract listener
- `data/ipfs/`  simulated IPFS buckets (CID metadata)
- `data/filecoin/`  simulated Filecoin deal receipts

## Setup

1. **Create a Python virtual environment**

   ```powershell
   cd ZKP_snark_ver
   .\scripts\setup_env.ps1
   # or on bash
   bash scripts/setup_env.sh
   ```

   Activate it afterwards (`venv\Scripts\Activate.ps1` on PowerShell, `source venv/bin/activate` on bash).

2. **Configure environment (optional)**

   Copy `.env.example` to `.env` to override ports, hostnames or enable a real SNARK backend.

3. **Start the demo**

   With the virtualenv active, run all processes:

   ```powershell
   python -m scripts.run_all
   ```

   Alternatively launch services individually:

   ```powershell
   uvicorn services.device_a.app:app --host 127.0.0.1 --port 8001
   uvicorn services.device_b.app:app --host 127.0.0.1 --port 8002
   uvicorn services.snark_runner.app:app --host 127.0.0.1 --port 8003
   python -m services.smart_contract.listener
   python -m services.storage.ipfs
   python -m services.storage.filecoin
   ```

4. **Interact**

   - Open `http://127.0.0.1:8001/ui` for the sender dashboard.
   - Proofs are generated via `/prove` on the SNARK runner, with metadata written under `data/proofs`.
   - Device Bs balance is observable at `http://127.0.0.1:8002/balance`.

## SNARK backend options

### Optional storage integrations

Set the following variables in your .env to push proofs to real services (fallback mocks run when unset):

- `PINATA_JWT`: Pinata JWT for `pinFileToIPFS` uploads
- `LIGHTHOUSE_API_KEY`: Lighthouse API key for Filecoin deal uploads


The runner uses a pluggable backend defined in `services/snark_runner/snark_pipeline.py`:

- **Mock Groth16 (`mock-groth16`)**  default, deterministic commitments plus integrity checks so the full workflow functions without external dependencies.
- **PySNARK (`pysnark-groth16`)**  blueprint for wiring an actual Groth16 prover. Install `pysnark>=0.7`, set `ENABLE_REAL_SNARK=true` in `.env`, and extend `services/snark_runner/pysnark_backend.py` with your proving key initialisation and proof export logic. Hook the resulting artefacts into `write_proof_artifacts(...)` so downstream services consume real proofs.

The backend selection is logged on startup (`GET /` on the runner also returns it) so Device As UI can display which prover is active.

### Integrating a concrete Groth16 circuit (outline)

1. Generate proving/verifying keys with your preferred tooling (PySNARK, Circom+snarkjs, gnark, ).
2. Implement the `prove_transfer` method in `pysnark_backend.py` to:
   - feed private/public inputs into the circuit,
   - return the proof bytes and public signals,
   - include any additional commitments so the smart-contract listener can verify the state transition.
3. Update `proof_artifacts.meta["backend"]` if you want to expose backend-specific diagnostics.

## Behavioural parity checklist

- **API contracts**  Device A still POSTs `/transfer`, Device B continues to expose `/update_balance`.
- **Proof workflow**  the runner materialises proof/public/witness triples per request and writes them under `data/proofs`, mirroring the old `output_proof.json` pipeline.
- **Downstream automations**  smart_contract listener and storage daemons react to filesystem events just like the StarkNet / Filecoin helpers in the original project.
- **Observability**  all services share the same logging format; every request is tagged with a `trace_id` propagated through proof artefacts.

## Testing & linting

To extend with unit tests, create modules under `tests/` and run them via `python -m pytest`. Static typing can be enforced with `ruff` or `mypy` once added to requirements.


