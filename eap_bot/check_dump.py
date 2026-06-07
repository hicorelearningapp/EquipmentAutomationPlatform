from source.schemas.report import ReportDefinition

r = ReportDefinition(RPTID='RPT_1', Name='Test', Type="Generated", Confidence=0.8, LinkedVIDs=[1])
print("Standard dump:", r.model_dump())
print("Exclude defaults:", r.model_dump(exclude_defaults=True))
print("Exclude unset:", r.model_dump(exclude_unset=True))
