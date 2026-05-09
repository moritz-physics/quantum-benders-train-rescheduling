import unittest

from qcedule.config import BACKEND, CONSTANTS, FILES

NET = FILES["net"]


class TestConfig(unittest.TestCase):
    """Tests the configfile."""

    def test_imports(self):
        # Check for any import errors
        print(CONSTANTS, FILES, BACKEND)

    def test_files(self):
        # Just check if no errors occur with filenames
        with open(NET, "rb") as f:
            print(f)


if __name__ == "__main__":
    unittest.main()
