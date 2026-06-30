"""Faker-based synthetic patient identity generation."""

from faker import Faker


# Input: `seed` fuer Faker-Reproduzierbarkeit, `locale` mit Faker-Locale.
# Output: Synthetische Identitaet mit Patient- und Accession-Feldern.
# Die Funktion erzeugt eine lokal reproduzierbare Faker-Identitaet.
def generate_identity(seed: int, locale: str = "en_US") -> dict[str, str]:
    fake = Faker(locale)
    fake.seed_instance(seed)

    last_name = fake.last_name()
    first_name = fake.first_name()
    patient_id = f"SYNTH-{fake.numerify(text='######')}"
    birth_date = fake.date_of_birth(minimum_age=18, maximum_age=90).strftime("%Y%m%d")
    patient_sex = fake.random_element(elements=["M", "F"])
    accession_number = f"ACC-{fake.numerify(text='#######')}"

    return {
        "patient_name": f"{last_name}^{first_name}",
        "patient_id": patient_id,
        "patient_birth_date": birth_date,
        "patient_sex": patient_sex,
        "accession_number": accession_number,
    }


if __name__ == "__main__":
    identity = generate_identity(seed=42)
    for key, value in identity.items():
        print(f"{key}: {value}")
