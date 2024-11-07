class DBM:
    name: str

    def __init__(self) -> None: ...
    def Open(
        self,
        path: str,
        rw: bool,
        no_create: bool,
        no_wait: bool,
        truncate: bool,
        dbm: str,
    ) -> DBM: ...
    def OrDie(self): ...
    def Get(self, bytes) -> bytes: ...
