from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


ENTITY_FILES = {
    "patients": "patients.csv",
    "encounters": "encounters.csv",
    "conditions": "conditions.csv",
    "medications": "medications.csv",
    "procedures": "procedures.csv",
    "observations": "observations.csv",
}

CODE_COLUMNS = {
    "encounters": "CODE",
    "conditions": "CODE",
    "medications": "CODE",
    "procedures": "CODE",
    "observations": "CODE",
}

DESCRIPTION_COLUMNS = {
    "encounters": "DESCRIPTION",
    "conditions": "DESCRIPTION",
    "medications": "DESCRIPTION",
    "procedures": "DESCRIPTION",
    "observations": "DESCRIPTION",
}

DATE_COLUMNS = {
    "patients": ["BIRTHDATE", "DEATHDATE"],
    "encounters": ["START", "STOP"],
    "conditions": ["START", "STOP"],
    "medications": ["START", "STOP"],
    "procedures": ["START", "STOP"],
    "observations": ["DATE"],
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Compara las salidas CSV raw de Synthea y Psynthea "
            "y genera resúmenes reproducibles."
        )
    )
    parser.add_argument(
        "--synthea",
        required=True,
        type=Path,
        help="Directorio CSV raw de Synthea.",
    )
    parser.add_argument(
        "--psynthea",
        required=True,
        type=Path,
        help="Directorio CSV raw de Psynthea.",
    )
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="Directorio donde se guardarán los resultados.",
    )
    parser.add_argument(
        "--reference-date",
        default="2024-12-31",
        help="Fecha de referencia para calcular edad. Por defecto: 2024-12-31.",
    )
    return parser.parse_args()


def resolve_csv_root(root: Path) -> Path:
    candidates = (
        root,
        root / "csv",
        root / "synthea" / "csv",
    )

    for candidate in candidates:
        if (candidate / "patients.csv").exists():
            return candidate

    raise FileNotFoundError(
        f"No se encontró patients.csv bajo: {root}"
    )


def read_csv(root: Path, filename: str) -> pd.DataFrame:
    path = root / filename

    if not path.exists():
        return pd.DataFrame()

    return pd.read_csv(path, low_memory=False)


def normalise_dates(
    dataframe: pd.DataFrame,
    columns: list[str],
) -> pd.DataFrame:
    result = dataframe.copy()

    for column in columns:
        if column in result.columns:
            result[column] = pd.to_datetime(
                result[column],
                errors="coerce",
                utc=True,
            )

    return result


def safe_series(
    dataframe: pd.DataFrame,
    column: str,
) -> pd.Series:
    if column not in dataframe.columns:
        return pd.Series(dtype="object")

    return dataframe[column]


def calculate_age(
    birthdates: pd.Series,
    reference_date: pd.Timestamp,
) -> pd.Series:
    birthdates = pd.to_datetime(
        birthdates,
        errors="coerce",
        utc=True,
    )

    reference = pd.Timestamp(reference_date)

    if reference.tzinfo is None:
        reference = reference.tz_localize("UTC")
    else:
        reference = reference.tz_convert("UTC")

    age = (
        reference.year
        - birthdates.dt.year
        - (
            (
                (reference.month < birthdates.dt.month)
                | (
                    (reference.month == birthdates.dt.month)
                    & (reference.day < birthdates.dt.day)
                )
            )
        ).astype("Int64")
    )

    return age.astype("Float64")


def numeric_summary(series: pd.Series) -> dict[str, Any]:
    values = pd.to_numeric(series, errors="coerce").dropna()

    if values.empty:
        return {
            "count": 0,
            "mean": None,
            "median": None,
            "std": None,
            "min": None,
            "max": None,
        }

    return {
        "count": int(values.count()),
        "mean": float(values.mean()),
        "median": float(values.median()),
        "std": float(values.std(ddof=1)) if len(values) > 1 else 0.0,
        "min": float(values.min()),
        "max": float(values.max()),
    }


def format_number(value: Any, decimals: int = 2) -> str:
    if value is None or pd.isna(value):
        return "NA"

    if isinstance(value, (int, np.integer)):
        return f"{int(value):,}"

    return f"{float(value):,.{decimals}f}"


def print_section(title: str) -> None:
    print()
    print("=" * 80)
    print(title)
    print("=" * 80)


def print_pair(
    label: str,
    synthea_value: Any,
    psynthea_value: Any,
) -> None:
    print(f"{label}")
    print(f"  Synthea : {synthea_value}")
    print(f"  Psynthea: {psynthea_value}")


def build_count_diff(
    synthea: pd.DataFrame,
    psynthea: pd.DataFrame,
    *,
    key_column: str,
    description_column: str | None = None,
) -> pd.DataFrame:
    def aggregate(dataframe: pd.DataFrame, simulator: str) -> pd.DataFrame:
        if dataframe.empty or key_column not in dataframe.columns:
            columns = [key_column, f"{simulator}_count"]

            if description_column:
                columns.insert(1, description_column)

            return pd.DataFrame(columns=columns)

        working = dataframe.copy()
        working[key_column] = (
            working[key_column]
            .astype("string")
            .fillna("<NA>")
        )

        group_columns = [key_column]

        if description_column and description_column in working.columns:
            working[description_column] = (
                working[description_column]
                .astype("string")
                .fillna("")
            )
            group_columns.append(description_column)

        result = (
            working.groupby(group_columns, dropna=False)
            .size()
            .rename(f"{simulator}_count")
            .reset_index()
        )

        return result

    synthea_counts = aggregate(synthea, "synthea")
    psynthea_counts = aggregate(psynthea, "psynthea")

    merge_columns = [key_column]

    if (
        description_column
        and description_column in synthea_counts.columns
        and description_column in psynthea_counts.columns
    ):
        merge_columns.append(description_column)

    result = synthea_counts.merge(
        psynthea_counts,
        on=merge_columns,
        how="outer",
    )

    result["synthea_count"] = (
        result["synthea_count"].fillna(0).astype(int)
    )
    result["psynthea_count"] = (
        result["psynthea_count"].fillna(0).astype(int)
    )

    result["absolute_difference"] = (
        result["psynthea_count"] - result["synthea_count"]
    )

    result["relative_difference_pct"] = np.where(
        result["synthea_count"] > 0,
        (
            result["absolute_difference"]
            / result["synthea_count"]
            * 100
        ),
        np.where(
            result["psynthea_count"] > 0,
            np.inf,
            0.0,
        ),
    )

    result["absolute_magnitude"] = (
        result["absolute_difference"].abs()
    )

    return result.sort_values(
        ["absolute_magnitude", "synthea_count", "psynthea_count"],
        ascending=[False, False, False],
    ).drop(columns=["absolute_magnitude"])


def patient_summary(
    patients: pd.DataFrame,
    reference_date: pd.Timestamp,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "rows": int(len(patients)),
        "unique_patients": 0,
        "age": numeric_summary(pd.Series(dtype=float)),
        "gender": {},
        "alive": None,
        "dead": None,
    }

    if patients.empty:
        return result

    id_column = "Id" if "Id" in patients.columns else "ID"

    if id_column in patients.columns:
        result["unique_patients"] = int(
            patients[id_column].nunique(dropna=True)
        )

    if "BIRTHDATE" in patients.columns:
        result["age"] = numeric_summary(
            calculate_age(
                patients["BIRTHDATE"],
                reference_date,
            )
        )

    if "GENDER" in patients.columns:
        result["gender"] = {
            str(key): int(value)
            for key, value in (
                patients["GENDER"]
                .astype("string")
                .fillna("<NA>")
                .value_counts(dropna=False)
                .to_dict()
                .items()
            )
        }

    if "DEATHDATE" in patients.columns:
        dead = int(patients["DEATHDATE"].notna().sum())
        result["dead"] = dead
        result["alive"] = int(len(patients) - dead)

    return result


def entity_summary(
    dataframe: pd.DataFrame,
    entity: str,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "rows": int(len(dataframe)),
        "unique_patients": 0,
        "date_min": None,
        "date_max": None,
    }

    if dataframe.empty:
        return result

    patient_column = "PATIENT"

    if patient_column in dataframe.columns:
        result["unique_patients"] = int(
            dataframe[patient_column].nunique(dropna=True)
        )

    date_candidates = DATE_COLUMNS.get(entity, [])

    for column in date_candidates:
        if column not in dataframe.columns:
            continue

        values = pd.to_datetime(
            dataframe[column],
            errors="coerce",
            utc=True,
        ).dropna()

        if values.empty:
            continue

        minimum = values.min()
        maximum = values.max()

        if (
            result["date_min"] is None
            or minimum.isoformat() < result["date_min"]
        ):
            result["date_min"] = minimum.isoformat()

        if (
            result["date_max"] is None
            or maximum.isoformat() > result["date_max"]
        ):
            result["date_max"] = maximum.isoformat()

    return result


def encounters_per_patient(
    encounters: pd.DataFrame,
) -> pd.Series:
    if encounters.empty or "PATIENT" not in encounters.columns:
        return pd.Series(dtype=float)

    return encounters.groupby("PATIENT").size()


def encounter_duration_hours(
    encounters: pd.DataFrame,
) -> pd.Series:
    if (
        encounters.empty
        or "START" not in encounters.columns
        or "STOP" not in encounters.columns
    ):
        return pd.Series(dtype=float)

    start = pd.to_datetime(
        encounters["START"],
        errors="coerce",
        utc=True,
    )
    stop = pd.to_datetime(
        encounters["STOP"],
        errors="coerce",
        utc=True,
    )

    return (stop - start).dt.total_seconds() / 3600


def yearly_counts(
    dataframe: pd.DataFrame,
    date_column: str,
) -> pd.DataFrame:
    if dataframe.empty or date_column not in dataframe.columns:
        return pd.DataFrame(columns=["year", "count"])

    dates = pd.to_datetime(
        dataframe[date_column],
        errors="coerce",
        utc=True,
    )

    result = (
        dates.dropna()
        .dt.year
        .value_counts()
        .sort_index()
        .rename_axis("year")
        .rename("count")
        .reset_index()
    )

    return result


def merge_yearly_counts(
    synthea: pd.DataFrame,
    psynthea: pd.DataFrame,
    date_column: str,
) -> pd.DataFrame:
    synthea_years = yearly_counts(
        synthea,
        date_column,
    ).rename(columns={"count": "synthea_count"})

    psynthea_years = yearly_counts(
        psynthea,
        date_column,
    ).rename(columns={"count": "psynthea_count"})

    result = synthea_years.merge(
        psynthea_years,
        on="year",
        how="outer",
    )

    if result.empty:
        return pd.DataFrame(
            columns=[
                "year",
                "synthea_count",
                "psynthea_count",
                "absolute_difference",
                "relative_difference_pct",
            ]
        )

    result["synthea_count"] = (
        result["synthea_count"].fillna(0).astype(int)
    )
    result["psynthea_count"] = (
        result["psynthea_count"].fillna(0).astype(int)
    )
    result["absolute_difference"] = (
        result["psynthea_count"] - result["synthea_count"]
    )
    result["relative_difference_pct"] = np.where(
        result["synthea_count"] > 0,
        (
            result["absolute_difference"]
            / result["synthea_count"]
            * 100
        ),
        np.where(
            result["psynthea_count"] > 0,
            np.inf,
            0.0,
        ),
    )

    return result.sort_values("year")


def observation_linkage_summary(
    observations: pd.DataFrame,
) -> dict[str, Any]:
    total = int(len(observations))

    if total == 0 or "ENCOUNTER" not in observations.columns:
        return {
            "total": total,
            "linked": 0,
            "unlinked": total,
            "linked_pct": 0.0,
        }

    encounter_ids = (
        observations["ENCOUNTER"]
        .astype("string")
        .str.strip()
    )

    linked_mask = (
        encounter_ids.notna()
        & encounter_ids.ne("")
        & encounter_ids.ne("<NA>")
        & encounter_ids.ne("nan")
    )

    linked = int(linked_mask.sum())

    return {
        "total": total,
        "linked": linked,
        "unlinked": int(total - linked),
        "linked_pct": (
            linked / total * 100
            if total > 0
            else 0.0
        ),
    }


def print_top_differences(
    dataframe: pd.DataFrame,
    *,
    key_column: str,
    description_column: str | None,
    limit: int = 15,
) -> None:
    if dataframe.empty:
        print("Sin datos.")
        return

    columns = [
        key_column,
        "synthea_count",
        "psynthea_count",
        "absolute_difference",
        "relative_difference_pct",
    ]

    if (
        description_column
        and description_column in dataframe.columns
    ):
        columns.insert(1, description_column)

    printable = dataframe[columns].head(limit).copy()

    printable["relative_difference_pct"] = printable[
        "relative_difference_pct"
    ].replace(
        {
            np.inf: "INF",
            -np.inf: "-INF",
        }
    )

    print(printable.to_string(index=False))


def main() -> None:
    args = parse_args()

    synthea_root = resolve_csv_root(args.synthea)
    psynthea_root = resolve_csv_root(args.psynthea)

    args.output.mkdir(parents=True, exist_ok=True)

    reference_date = pd.Timestamp(args.reference_date)

    datasets: dict[str, dict[str, pd.DataFrame]] = {
        "synthea": {},
        "psynthea": {},
    }

    for entity, filename in ENTITY_FILES.items():
        datasets["synthea"][entity] = normalise_dates(
            read_csv(synthea_root, filename),
            DATE_COLUMNS.get(entity, []),
        )
        datasets["psynthea"][entity] = normalise_dates(
            read_csv(psynthea_root, filename),
            DATE_COLUMNS.get(entity, []),
        )

    summary: dict[str, Any] = {
        "inputs": {
            "synthea": str(synthea_root),
            "psynthea": str(psynthea_root),
            "reference_date": args.reference_date,
        },
        "patients": {},
        "entities": {},
        "entity_differences": {},
    }

    print_section("COHORTE")

    synthea_patients = patient_summary(
        datasets["synthea"]["patients"],
        reference_date,
    )
    psynthea_patients = patient_summary(
        datasets["psynthea"]["patients"],
        reference_date,
    )

    summary["patients"] = {
        "synthea": synthea_patients,
        "psynthea": psynthea_patients,
    }

    print_pair(
        "Pacientes",
        synthea_patients["rows"],
        psynthea_patients["rows"],
    )

    print()
    print("Edad")
    print(
        "  Synthea : "
        f"media={format_number(synthea_patients['age']['mean'])}, "
        f"mediana={format_number(synthea_patients['age']['median'])}, "
        f"std={format_number(synthea_patients['age']['std'])}, "
        f"min={format_number(synthea_patients['age']['min'])}, "
        f"max={format_number(synthea_patients['age']['max'])}"
    )
    print(
        "  Psynthea: "
        f"media={format_number(psynthea_patients['age']['mean'])}, "
        f"mediana={format_number(psynthea_patients['age']['median'])}, "
        f"std={format_number(psynthea_patients['age']['std'])}, "
        f"min={format_number(psynthea_patients['age']['min'])}, "
        f"max={format_number(psynthea_patients['age']['max'])}"
    )

    print()
    print("Sexo")
    print(f"  Synthea : {synthea_patients['gender']}")
    print(f"  Psynthea: {psynthea_patients['gender']}")

    for entity in (
        "encounters",
        "conditions",
        "medications",
        "procedures",
        "observations",
    ):
        synthea_df = datasets["synthea"][entity]
        psynthea_df = datasets["psynthea"][entity]

        synthea_entity_summary = entity_summary(
            synthea_df,
            entity,
        )
        psynthea_entity_summary = entity_summary(
            psynthea_df,
            entity,
        )

        summary["entities"][entity] = {
            "synthea": synthea_entity_summary,
            "psynthea": psynthea_entity_summary,
        }

        synthea_rows = len(synthea_df)
        psynthea_rows = len(psynthea_df)
        difference = psynthea_rows - synthea_rows
        relative_difference = (
            difference / synthea_rows * 100
            if synthea_rows > 0
            else None
        )

        summary["entity_differences"][entity] = {
            "synthea_rows": int(synthea_rows),
            "psynthea_rows": int(psynthea_rows),
            "absolute_difference": int(difference),
            "relative_difference_pct": (
                float(relative_difference)
                if relative_difference is not None
                else None
            ),
        }

        print_section(entity.upper())

        print_pair(
            "Filas",
            f"{synthea_rows:,}",
            f"{psynthea_rows:,}",
        )
        print(
            "Diferencia Psynthea - Synthea: "
            f"{difference:+,} "
            f"({format_number(relative_difference)}%)"
        )

        print_pair(
            "Pacientes únicos",
            synthea_entity_summary["unique_patients"],
            psynthea_entity_summary["unique_patients"],
        )

        print_pair(
            "Rango temporal",
            (
                f"{synthea_entity_summary['date_min']} -> "
                f"{synthea_entity_summary['date_max']}"
            ),
            (
                f"{psynthea_entity_summary['date_min']} -> "
                f"{psynthea_entity_summary['date_max']}"
            ),
        )

        code_column = CODE_COLUMNS.get(entity)
        description_column = DESCRIPTION_COLUMNS.get(entity)

        if code_column:
            diff = build_count_diff(
                synthea_df,
                psynthea_df,
                key_column=code_column,
                description_column=description_column,
            )

            output_path = (
                args.output
                / f"{entity}_code_diff.csv"
            )
            diff.to_csv(output_path, index=False)

            print()
            print("Mayores diferencias por código")
            print_top_differences(
                diff,
                key_column=code_column,
                description_column=description_column,
            )

        if entity == "encounters":
            encounter_class_diff = build_count_diff(
                synthea_df,
                psynthea_df,
                key_column="ENCOUNTERCLASS",
            )
            encounter_class_diff.to_csv(
                args.output / "encounter_class_diff.csv",
                index=False,
            )

            yearly_diff = merge_yearly_counts(
                synthea_df,
                psynthea_df,
                "START",
            )
            yearly_diff.to_csv(
                args.output / "encounter_year_diff.csv",
                index=False,
            )

            synthea_per_patient = numeric_summary(
                encounters_per_patient(synthea_df)
            )
            psynthea_per_patient = numeric_summary(
                encounters_per_patient(psynthea_df)
            )

            synthea_duration = numeric_summary(
                encounter_duration_hours(synthea_df)
            )
            psynthea_duration = numeric_summary(
                encounter_duration_hours(psynthea_df)
            )

            summary["encounter_details"] = {
                "per_patient": {
                    "synthea": synthea_per_patient,
                    "psynthea": psynthea_per_patient,
                },
                "duration_hours": {
                    "synthea": synthea_duration,
                    "psynthea": psynthea_duration,
                },
            }

            print()
            print("Encuentros por clase")
            print_top_differences(
                encounter_class_diff,
                key_column="ENCOUNTERCLASS",
                description_column=None,
            )

            print()
            print("Encuentros por paciente")
            print(
                "  Synthea : "
                f"media={format_number(synthea_per_patient['mean'])}, "
                f"mediana={format_number(synthea_per_patient['median'])}, "
                f"std={format_number(synthea_per_patient['std'])}, "
                f"min={format_number(synthea_per_patient['min'])}, "
                f"max={format_number(synthea_per_patient['max'])}"
            )
            print(
                "  Psynthea: "
                f"media={format_number(psynthea_per_patient['mean'])}, "
                f"mediana={format_number(psynthea_per_patient['median'])}, "
                f"std={format_number(psynthea_per_patient['std'])}, "
                f"min={format_number(psynthea_per_patient['min'])}, "
                f"max={format_number(psynthea_per_patient['max'])}"
            )

            print()
            print("Duración de encuentros, horas")
            print(
                "  Synthea : "
                f"media={format_number(synthea_duration['mean'])}, "
                f"mediana={format_number(synthea_duration['median'])}, "
                f"max={format_number(synthea_duration['max'])}"
            )
            print(
                "  Psynthea: "
                f"media={format_number(psynthea_duration['mean'])}, "
                f"mediana={format_number(psynthea_duration['median'])}, "
                f"max={format_number(psynthea_duration['max'])}"
            )

        if entity == "observations":
            synthea_linkage = observation_linkage_summary(
                synthea_df
            )
            psynthea_linkage = observation_linkage_summary(
                psynthea_df
            )

            summary["observation_linkage"] = {
                "synthea": synthea_linkage,
                "psynthea": psynthea_linkage,
            }

            print()
            print("Vinculación de observaciones con encuentros")
            print(
                "  Synthea : "
                f"{synthea_linkage['linked']:,}/"
                f"{synthea_linkage['total']:,} "
                f"({synthea_linkage['linked_pct']:.2f}%)"
            )
            print(
                "  Psynthea: "
                f"{psynthea_linkage['linked']:,}/"
                f"{psynthea_linkage['total']:,} "
                f"({psynthea_linkage['linked_pct']:.2f}%)"
            )

    print_section("RESUMEN GLOBAL")

    global_rows = []

    for entity, values in summary[
        "entity_differences"
    ].items():
        global_rows.append(
            {
                "entity": entity,
                **values,
            }
        )

    global_diff = pd.DataFrame(global_rows)
    global_diff["absolute_magnitude"] = (
        global_diff["absolute_difference"].abs()
    )
    global_diff = global_diff.sort_values(
        "absolute_magnitude",
        ascending=False,
    ).drop(columns=["absolute_magnitude"])

    global_diff.to_csv(
        args.output / "entity_summary.csv",
        index=False,
    )

    print(global_diff.to_string(index=False))

    summary_path = args.output / "summary.json"
    summary_path.write_text(
        json.dumps(
            summary,
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        ),
        encoding="utf-8",
    )

    print()
    print(f"Resultados guardados en: {args.output.resolve()}")
    print(f"Resumen JSON: {summary_path.resolve()}")


if __name__ == "__main__":
    main()