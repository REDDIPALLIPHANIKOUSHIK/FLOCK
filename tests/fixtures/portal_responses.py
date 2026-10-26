"""Observed and synthetic test fixtures modeling upstream Urja portal responses."""

# 1. Login success response (sets cookie + returns redirect)
LOGIN_SUCCESS_BODY = '{"type":"redirect","status":303,"location":"/meters"}'

# 2. Login failure response (HTTP 200 with failure type)
LOGIN_FAILURE_BODY = '{"type":"failure","status":401,"data":"[{\\"email\\":1,\\"error\\":2},\\"operator@urja.local\\",\\"Invalid email or password.\\"]"}'

# 3. Session expired redirect
SESSION_EXPIRED_BODY = '{"type":"redirect","location":"/login"}'

# 4. Meters search response
METERS_SEARCH_PAGE_1 = {
    "data": [
        {
            "meterId": "J100000",
            "serialNo": "SE33962",
            "make": "HPL",
            "phaseType": "single",
            "installStatus": "Decommissioned",
            "dtCode": "DT-001"
        },
        {
            "meterId": "J100001",
            "serialNo": "GE84132",
            "make": "L&T",
            "phaseType": "single",
            "installStatus": "Installed",
            "dtCode": "DT-002"
        },
        {
            "meterId": "J100020",
            "serialNo": "AL20290",
            "make": "Allied",
            "phaseType": "three",
            "installStatus": "Installed",
            "dtCode": "DT-021"
        }
    ],
    "total": 403
}

# 5. Meter J100000 deval data (legacy build)
METER_J100000_DEVAL = {
    "type": "data",
    "nodes": [
        None,
        {
            "type": "data",
            "data": [
                {"user": 1},
                {"name": 2, "email": 3},
                "Ops Desk",
                "operator@urja.local"
            ],
            "uses": {}
        },
        {
            "type": "data",
            "data": [
                {"meterId": 1, "detail": 2, "hierarchy": 21},
                "J100000",
                {"data": 3},
                [4, 6, 9, 12, 15, 18],
                {"parameterName": 5, "parameterValue": 1},
                "Meter ID",
                {"parameterName": 7, "parameterValue": 8},
                "Serial No",
                "SE33962",
                {"parameterName": 10, "parameterValue": 11},
                "Make",
                "HPL",
                {"parameterName": 13, "parameterValue": 14},
                "Phase Type",
                "single",
                {"parameterName": 16, "parameterValue": 17},
                "Installation Status",
                "Decommissioned",
                {"parameterName": 19, "parameterValue": 20},
                "Installation Type",
                "Whole Current",
                {
                    "Meter ID": 1,
                    "Installation Status": 17,
                    "Installation Type": 20,
                    "Zone": 22,
                    "Circle": 23,
                    "Division": 24,
                    "Subdivision": 25,
                    "Sub Station": 26,
                    "Feeder": 27,
                    "DT": 28
                },
                "Jaipur Zone 1 (Z-01)",
                "Circle 1 (C-01)",
                "Division 1 (D-01)",
                "Subdivision 1 (SD-01)",
                "Substation 1 (SS-01)",
                "Feeder 1 (F-001)",
                "Malviya Nagar DT 1 (DT-001)"
            ],
            "uses": {"params": ["id"]}
        }
    ]
}

# 6. Meter J100020 deval data (v2 classData build)
METER_J100020_DEVAL = {
    "type": "data",
    "nodes": [
        None,
        {
            "type": "data",
            "data": [
                {"user": 1},
                {"name": 2, "email": 3},
                "Ops Desk",
                "operator@urja.local"
            ],
            "uses": {}
        },
        {
            "type": "data",
            "data": [
                {"meterId": 1, "detail": 2, "hierarchy": 4},
                "J100020",
                {"classData": 3},
                '{"installed_meter":{"MeterId":"J100020","SerialNo":"AL20290","Make":"Allied","PhaseType":"three","InstallationStatus":"Installed","InstallationType":"CT Operated"}}',
                {
                    "Meter ID": 1,
                    "Installation Status": 5,
                    "Installation Type": 6,
                    "Zone": 7,
                    "Circle": 8,
                    "Division": 9,
                    "Subdivision": 10,
                    "Sub Station": 11,
                    "Feeder": 12,
                    "DT": 13
                },
                "Installed",
                "CT Operated",
                "Jaipur Zone 3 (Z-03)",
                "Circle 3 (C-03)",
                "Division 1 (D-01)",
                "Subdivision 7 (SD-07)",
                "Substation 3 (SS-03)",
                "Feeder 21 (F-021)",
                "Malviya Nagar DT 21 (DT-021)"
            ],
            "uses": {"params": ["id"]}
        }
    ]
}

# 7. Meter J100000 Geo Coordinates
METER_J100000_GEO = {
    "data": {
        "latitude": "26.938961002479868",
        "longitude": "75.83095696146852"
    }
}

# 8. Meter J100000 Energy Readings
METER_J100000_ENERGY = {
    "data": [
        {"timestamp": "24/06/2026 00:00", "kwh": "48439.16", "kvah": "52314.29", "voltR": "229"},
        {"timestamp": "24/06/2026 00:30", "kwh": "48439.58", "kvah": "52314.75", "voltR": "220"},
        {"timestamp": "24/06/2026 01:00", "kwh": "48440.01", "kvah": "52315.20", "voltR": "224"},
    ]
}

# 9. Meter Not Found SvelteKit deval response
METER_NOT_FOUND_DEVAL = {
    "type": "data",
    "nodes": [
        None,
        {
            "type": "data",
            "data": [
                {"user": 1},
                {"name": 2, "email": 3},
                "Ops Desk",
                "operator@urja.local"
            ],
            "uses": {}
        },
        {
            "type": "error",
            "error": {"message": "Meter not found"},
            "status": 404
        }
    ]
}

# 10. Distribution Transformers response
DTS_RESPONSE = {
    "data": [
        {"code": "DT-001", "name": "Malviya Nagar DT 1", "feederCode": "F-001", "capacityKva": 100},
        {"code": "DT-002", "name": "Mansarovar DT 2", "feederCode": "F-002", "capacityKva": 63},
        {"code": "DT-003", "name": "Vaishali DT 3", "feederCode": "F-001", "capacityKva": 250}
    ],
    "total": 3
}

# 11. HTML SSR fixture for meter J100000
METER_HTML_FIXTURE = """
<!doctype html>
<html>
<body>
    <nav class="flex-wrap">
        <span>Jaipur Zone 1 (Z-01)</span>
        <span>›</span>
        <span>Circle 1 (C-01)</span>
        <span>›</span>
        <span>Malviya Nagar DT 1 (DT-001)</span>
    </nav>
    <dl>
        <div><dt>Meter ID</dt><dd>J100000</dd></div>
        <div><dt>Serial No</dt><dd>SE33962</dd></div>
        <div><dt>Make</dt><dd>HPL</dd></div>
        <div><dt>Phase Type</dt><dd>single</dd></div>
        <div><dt>Installation Status</dt><dd>Decommissioned</dd></div>
        <div><dt>Installation Type</dt><dd>Whole Current</dd></div>
    </dl>
</body>
</html>
"""
