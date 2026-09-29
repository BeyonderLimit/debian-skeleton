"""Allow ``python3 -m debian_skeleton`` from a copied src tree, without pip."""

import sys

from debian_skeleton.cli import main

if __name__ == "__main__":
    sys.exit(main())
