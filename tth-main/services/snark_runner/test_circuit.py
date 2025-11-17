from __future__ import annotations

from pysnark.runtime import Var

def test_circuit():
    # Simple test: prove that a number is positive
    print("Starting test circuit...")
    
    x = 10
    print(f"Input value x = {x}")
    
    x_var = Var(x)
    print("Created Var instance for x")
    
    # Assert x is positive by proving it has a valid bit decomposition
    # This will throw an error if x is not positive
    print("Checking if x is positive...")
    x_var.assert_positive(x.bit_length())
    print("Successfully proved x is positive!")
    
    result = {"x": x}
    print(f"Test completed. Result: {result}")
    return result

if __name__ == "__main__":
    try:
        result = test_circuit()
        print("\nCircuit execution successful!")
        print(f"Final values: {result}")
    except Exception as e:
        print(f"\nError during circuit execution: {str(e)}")