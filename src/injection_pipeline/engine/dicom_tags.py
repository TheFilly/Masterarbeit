"""DICOM tag injection helpers."""

import pydicom


# Input: `ds` mit DICOM-Dataset, `tag_map` mit Keyword-zu-Wert-Mapping.
# Output: Dasselbe Dataset mit aktualisierten Tags.
# Die Funktion mutiert das Dataset in-place.
def inject_tags(ds: pydicom.Dataset, tag_map: dict[str, str]) -> pydicom.Dataset:
    for keyword, value in tag_map.items():
        setattr(ds, keyword, value)
    return ds
