# DATA-01 SQLite 与 Alembic 基础

运行和迁移共用 `create_sqlite_engine(database_path)`，使数据库路径和连接行为一致。引擎会创建父目录，首次连接才创建数据库文件。`create_session_factory(engine)` 提供短生命周期的会话，调用方可以用 `with sessions.begin() as session` 在同一个事务中提交或回滚。

SQLite 的外键校验按连接生效。引擎在每条新连接进入连接池前启用外键，并使用 Python 3.12 的事务模式。在线迁移把迁移操作和版本标记放在同一个数据库事务中。基线 `0001` 只建立版本记录，业务表由后续迁移定义。
[SQLAlchemy 的 SQLite 事务与外键说明](https://docs.sqlalchemy.org/en/21/dialects/sqlite.html#transactions-with-sqlite-and-the-sqlite3-driver) · [Alembic 迁移事务示例](https://alembic.sqlalchemy.org/en/latest/cookbook.html#sharing-a-connection-across-one-or-more-programmatic-migration-commands)

在仓库根目录运行以下命令，可以用独立数据库验证迁移。

```sh
uv run alembic -x database_path=tmp/verification.sqlite3 upgrade head
uv run alembic -x database_path=tmp/verification.sqlite3 current
uv run alembic -x database_path=tmp/verification.sqlite3 downgrade base
```

升级后的版本为 `0001`，降级后没有当前版本。不传 `-x database_path=...` 时，默认使用与 `alembic.ini` 同级的 `runs.sqlite3`。加上 `upgrade head --sql` 可以预览基线 SQL。
