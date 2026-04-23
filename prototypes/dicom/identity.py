"""Faker-based synthetic patient identity generation."""

from faker import Faker


def generate_identity(seed: int, locale: str = "en_US") -> dict[str, str]:
    """Generate a reproducible synthetic patient identity.

    Args:
        seed: Deterministic seed for the Faker instance.
        locale: Faker locale string (e.g. "en_US", "de_DE").

    Returns:
        Dict with keys: patient_name, patient_id, patient_birth_date,
        patient_sex, accession_number.
    """
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
