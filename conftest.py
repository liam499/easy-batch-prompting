"""Make ``import aieasybatch`` work from the src/ layout without an install."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent / "src"))
