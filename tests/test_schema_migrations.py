from sqlalchemy import create_engine, inspect

from app.database import migrate_component_cui_fields


def test_component_cui_migration_adds_columns_to_existing_schema():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            """
            CREATE TABLE component (
                id INTEGER PRIMARY KEY,
                equipment_id INTEGER NOT NULL,
                name VARCHAR(50) NOT NULL,
                t_min_mm FLOAT NOT NULL,
                t_nominal_mm FLOAT NOT NULL,
                geometry_type VARCHAR(30) NOT NULL
            )
            """
        )

    migrate_component_cui_fields(engine)
    migrate_component_cui_fields(engine)

    columns = {column["name"] for column in inspect(engine).get_columns("component")}
    assert {"insulated", "operating_temperature_c"} <= columns
