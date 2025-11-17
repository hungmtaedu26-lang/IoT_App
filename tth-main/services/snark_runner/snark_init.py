from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Dict

from pysnark.runtime import snark_init

logger = logging.getLogger(__name__)

def initialize_pysnark(trace_id: str) -> None:
    """Initialize PySNARK with required keys and directories."""
    from shared.config import get_settings
    data_dir = get_settings().data_dir / "pysnark" / trace_id
    data_dir.mkdir(parents=True, exist_ok=True)
    
    # Set environment variables for PySNARK
    os.environ["PYSNARK_ENABLED"] = "1"
    os.environ["PYSNARK_PROVE"] = "1"
    os.environ["PYSNARK_REBUILD"] = "1"
    os.environ["PYSNARK_KEYDIR"] = str(data_dir)
    os.environ["PYSNARK_PROOFDIR"] = str(data_dir)
    
    # Make sure the qaptools executables are in PATH
    qaptools_path = os.path.join(os.path.dirname(__file__), "..", "..", "pysnark", "qaptools")
    if os.path.exists(qaptools_path):
        os.environ["QAPTOOLS_BIN"] = str(qaptools_path)
    
    # Initialize SNARK environment
    snark_init()