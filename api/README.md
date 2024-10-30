### Run tests and linting
    Tests:
    pytest
    
    Indent:
    ruff format src/refget
    
    Lint:
    ruff check src/refget
    
    Type check:
    MYPYPATH=src/stubs/ python -m mypy src/refget/
