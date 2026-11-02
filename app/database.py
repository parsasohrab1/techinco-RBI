from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.schema import CreateColumn

from .config import settings

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def migrate_component_cui_fields(database_engine: Engine = engine) -> None:
    from .models import Component

    table = Component.__table__
    with database_engine.begin() as connection:
        existing_columns = {
            column["name"] for column in inspect(connection).get_columns(table.name)
        }
        preparer = connection.dialect.identifier_preparer
        quoted_table = preparer.quote(table.name)

        for column_name in ("insulated", "operating_temperature_c"):
            if column_name in existing_columns:
                continue
            column = table.c[column_name]
            definition = CreateColumn(column).compile(dialect=connection.dialect)
            connection.exec_driver_sql(
                f"ALTER TABLE {quoted_table} ADD COLUMN {definition}"
            )


def migrate_damage_mechanism_assessment_data(database_engine: Engine = engine) -> None:
    from .models import ComponentDamageMechanism

    table = ComponentDamageMechanism.__table__
    with database_engine.begin() as connection:
        existing_columns = {
            column["name"] for column in inspect(connection).get_columns(table.name)
        }
        column_name = "assessment_data_json"
        if column_name in existing_columns:
            return

        preparer = connection.dialect.identifier_preparer
        quoted_table = preparer.quote(table.name)
        definition = CreateColumn(table.c[column_name]).compile(
            dialect=connection.dialect
        )
        connection.exec_driver_sql(
            f"ALTER TABLE {quoted_table} ADD COLUMN {definition}"
        )


def migrate_equipment_plant_unit(database_engine: Engine = engine) -> None:
    from .models import Equipment

    table = Equipment.__table__
    with database_engine.begin() as connection:
        existing_columns = {
            column["name"] for column in inspect(connection).get_columns(table.name)
        }
        column_name = "plant_unit"
        if column_name in existing_columns:
            return

        preparer = connection.dialect.identifier_preparer
        quoted_table = preparer.quote(table.name)
        definition = CreateColumn(table.c[column_name]).compile(
            dialect=connection.dialect
        )
        connection.exec_driver_sql(
            f"ALTER TABLE {quoted_table} ADD COLUMN {definition}"
        )
