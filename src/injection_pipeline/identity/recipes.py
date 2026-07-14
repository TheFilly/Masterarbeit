"""Faker recipe registry for schema-driven identity generation."""

from collections.abc import Callable
from datetime import date, datetime, timedelta
from typing import Any

from faker import Faker
from faker.providers.date_time import change_year, datetime_to_timestamp

Recipe = Callable[[Faker, dict[str, Any], date], str]


# Input: `arguments` aus dem Schema und erlaubte Schluesselmengen.
# Output: Keine Rueckgabe.
# Die Funktion meldet fehlende oder unbekannte Rezeptargumente vor dem
# Faker-Aufruf mit einer reproduzierbaren Fehlermeldung.
def _validate_argument_keys(
    arguments: dict[str, Any],
    *,
    required: set[str],
    allowed: set[str],
) -> None:
    missing = required - set(arguments)
    if missing:
        raise ValueError(f"Missing recipe arguments: {sorted(missing)}.")
    unexpected = set(arguments) - allowed
    if unexpected:
        raise ValueError(f"Unexpected recipe arguments: {sorted(unexpected)}.")


# Input: `arguments` aus dem Schema und `key` fuer den erwarteten String.
# Output: String-Wert fuer das Rezept.
# Die Funktion verhindert, dass Faker mit falsch typisierten Schemawerten
# aufgerufen wird.
def _require_string(arguments: dict[str, Any], key: str) -> str:
    value = arguments[key]
    if not isinstance(value, str):
        raise ValueError(f"Recipe argument {key!r} must be a string.")
    return value


# Input: `arguments` aus dem Schema und `key` fuer den erwarteten Integer.
# Output: Integer-Wert fuer das Rezept.
# Die Funktion haelt Altersgrenzen strikt numerisch.
def _require_int(arguments: dict[str, Any], key: str) -> int:
    value = arguments[key]
    if not isinstance(value, int):
        raise ValueError(f"Recipe argument {key!r} must be an integer.")
    return value


# Input: `fake` als geseedete Faker-Instanz, leeres Argumentmapping und Kontextdatum.
# Output: DICOM-Personenname im `Last^First`-Format.
# Die Funktion bewahrt die alte interne Aufrufreihenfolge: Nachname vor Vorname.
def dicom_person_name(
    fake: Faker,
    arguments: dict[str, Any],
    reference_date: date,
) -> str:
    _ = reference_date
    _validate_argument_keys(arguments, required=set(), allowed=set())
    last_name = str(fake.last_name())
    first_name = str(fake.first_name())
    return f"{last_name}^{first_name}"


# Input: `fake` als geseedete Faker-Instanz, `text`-Pattern und Kontextdatum.
# Output: Von Faker erzeugter Ziffernstring.
# Die Funktion kapselt den bisherigen `fake.numerify`-Aufruf fuer Schemafelder.
def numerify(
    fake: Faker,
    arguments: dict[str, Any],
    reference_date: date,
) -> str:
    _ = reference_date
    _validate_argument_keys(arguments, required={"text"}, allowed={"text"})
    return str(fake.numerify(text=_require_string(arguments, "text")))


# Input: `fake`, Alters-/Formatargumente und `reference_date` aus dem Schema.
# Output: Formatiertes Geburtsdatum.
# Die Funktion spiegelt Fakers Alterslogik am Schema-Referenzdatum und zieht
# den Sekunden-Offset selbst per `randint`, statt `fake.date_time_ad()` zu
# rufen: dessen `_rand_seconds` verzweigt in Faker selbst nach
# `platform.system()` (Windows: randint/int, sonst: uniform/float) und liefert
# bei gleichem Seed je nach Betriebssystem ein anderes Datum.
def date_of_birth(
    fake: Faker,
    arguments: dict[str, Any],
    reference_date: date,
) -> str:
    _validate_argument_keys(
        arguments,
        required={"minimum_age", "maximum_age", "format"},
        allowed={"minimum_age", "maximum_age", "format"},
    )
    minimum_age = _require_int(arguments, "minimum_age")
    maximum_age = _require_int(arguments, "maximum_age")
    if maximum_age < 0:
        raise ValueError("maximum_age must be greater than or equal to zero.")
    if minimum_age < 0:
        raise ValueError("minimum_age must be greater than or equal to zero.")
    if minimum_age > maximum_age:
        raise ValueError("minimum_age must be less than or equal to maximum_age.")

    start_date = change_year(reference_date, -(maximum_age + 1))
    end_date = change_year(reference_date, -minimum_age)
    start_seconds = datetime_to_timestamp(start_date)
    end_seconds = datetime_to_timestamp(end_date)
    birth_seconds = fake.random.randint(start_seconds, end_seconds)
    birth_date = (datetime(1970, 1, 1) + timedelta(seconds=birth_seconds)).date()
    if birth_date == start_date:
        birth_date += timedelta(days=1)
    if not isinstance(birth_date, date):
        raise ValueError("Faker date_of_birth returned a non-date value.")
    return birth_date.strftime(_require_string(arguments, "format"))


# Input: `fake` als geseedete Faker-Instanz, `elements` und Kontextdatum.
# Output: Von Faker ausgewaehltes Element.
# Die Funktion laesst die Auswahl weiter durch Faker treffen, damit Seeds gleich
# bleiben.
def random_element(
    fake: Faker,
    arguments: dict[str, Any],
    reference_date: date,
) -> str:
    _ = reference_date
    _validate_argument_keys(arguments, required={"elements"}, allowed={"elements"})
    elements = arguments["elements"]
    if not isinstance(elements, list) or not elements:
        raise ValueError("Recipe argument 'elements' must be a non-empty list.")
    if not all(isinstance(element, str) for element in elements):
        raise ValueError("Recipe argument 'elements' must contain only strings.")
    return str(fake.random_element(elements=elements))


RECIPES: dict[str, Recipe] = {
    "date_of_birth": date_of_birth,
    "dicom_person_name": dicom_person_name,
    "numerify": numerify,
    "random_element": random_element,
}


# Input: `recipe_name`, geseedete Faker-Instanz und Schemaargumente.
# Output: Generierter Rohwert vor Anwendung des Value-Templates.
# Die Funktion bildet den einzigen dynamischen Dispatchpunkt fuer Rezeptnamen.
def run_recipe(
    recipe_name: str,
    fake: Faker,
    arguments: dict[str, Any],
    reference_date: date,
) -> str:
    recipe = RECIPES.get(recipe_name)
    if recipe is None:
        raise ValueError(f"Unknown identity generation recipe: {recipe_name!r}.")
    return recipe(fake, arguments, reference_date)
