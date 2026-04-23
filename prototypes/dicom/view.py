from importlib import metadata

import pydicom
import matplotlib.pyplot as plt

ds = pydicom.dcmread("prototypes/dicom/output/echo_injected.dcm")
#ds = pydicom.dcmread("DycomData\\Anonymization\\deanonymized_with_labels\\patient_10005749_20010003\\annotations_cxr\\cxr_Allison_Hill_PID-876646_000.dcm")

# Tags prüfen
#print("PatientName:", ds.PatientName)
#print("PatientID:", ds.PatientID)
#print("PatientBirthDate:", ds.PatientBirthDate)

print(ds.file_meta)

# Bild anzeigen (erstes Frame bei Multi-Frame)
pixel_array = ds.pixel_array
frame = pixel_array[0] if pixel_array.ndim >= 3 and pixel_array.shape[0] > 1 else pixel_array
cmap = "gray" if frame.ndim == 2 else None
plt.imshow(frame, cmap=cmap)
plt.title(str(ds.PatientName))
plt.axis("off")
plt.savefig("prototypes/dicom/output/preview.png", dpi=150, bbox_inches="tight")
plt.show()
