from sqlalchemy import create_engine, inspect

from app.database import (
    migrate_component_cui_fields,
    migrate_damage_mechanism_assessment_data,
    migrate_equipment_plant_unit,
)


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


def test_damage_mechanism_migration_adds_assessment_data_to_existing_schema():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            """
            CREATE TABLE component_damage_mechanism (
                id INTEGER PRIMARY KEY,
                component_id INTEGER NOT NULL,
                dm_id INTEGER NOT NULL,
                status VARCHAR(10) NOT NULL,
                justification TEXT NOT NULL
            )
            """
        )

    migrate_damage_mechanism_assessment_data(engine)
    migrate_damage_mechanism_assessment_data(engine)

    columns = {
        column["name"]
        for column in inspect(engine).get_columns("component_damage_mechanism")
    }
    assert "assessment_data_json" in columns


def test_equipment_migration_adds_plant_unit_to_existing_schema():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            """
            CREATE TABLE equipment (
                id INTEGER PRIMARY KEY,
                tag_number VARCHAR(50) NOT NULL,
                equipment_type VARCHAR(30) NOT NULL
            )
            """
        )
        connection.exec_driver_sql(
            "INSERT INTO equipment (id, tag_number, equipment_type) "
            "VALUES (1, 'OLD-1', 'vessel')"
        )

    migrate_equipment_plant_unit(engine)
    migrate_equipment_plant_unit(engine)

    columns = {column["name"] for column in inspect(engine).get_columns("equipment")}
    assert "plant_unit" in columns
    with engine.connect() as connection:
        assert connection.exec_driver_sql(
            "SELECT plant_unit FROM equipment WHERE id = 1"
        ).scalar_one() == "Unassigned"
