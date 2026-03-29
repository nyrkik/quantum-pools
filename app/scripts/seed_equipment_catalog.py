"""Seed Equipment Catalog — common pool equipment + EMD-identified models.

Run: /home/brian/00_MyProjects/QuantumPools/venv/bin/python scripts/seed_equipment_catalog.py
"""

import asyncio
import sys
import os
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from src.core.database import get_db_context
from src.models.equipment_catalog import EquipmentCatalog

CATALOG = [
    # ═══════════════════════════════════════════════════════════
    # PUMPS — Pentair
    # ═══════════════════════════════════════════════════════════
    {"canonical_name": "Pentair IntelliFlo VSF", "equipment_type": "pump", "manufacturer": "Pentair", "model_number": "011056", "category": "Variable Speed Pump",
     "specs": {"hp": 3, "gpm_at_60tdh": 135, "voltage": 230}, "aliases": ["intelliflo vsf", "intelliflo 3 vsf", "pentair vsf", "011056", "vsf 3hp 135@60tdh"]},
    {"canonical_name": "Pentair IntelliFlo VS+SVRS 3HP", "equipment_type": "pump", "manufacturer": "Pentair", "model_number": "011028", "category": "Variable Speed Pump",
     "specs": {"hp": 3, "gpm_at_60tdh": 143, "voltage": 230}, "aliases": ["intelliflo vs-svrs", "intelliflo vs+svrs", "vs-svrs", "011028", "intelliflo 3hp", "intelliflo vs + svrs 3hp", "inteliflo vs+svrs", "intelliflo vs+svrs 3hp", "intelliflo"]},
    {"canonical_name": "Pentair IntelliFlo i1 1HP", "equipment_type": "pump", "manufacturer": "Pentair", "model_number": "011060", "category": "Variable Speed Pump",
     "specs": {"hp": 1, "gpm_at_60tdh": 74, "voltage": 230}, "aliases": ["intelliflo i1", "intelliflo i1 1hp", "011060", "intelliflo i1 1hp 74gpm@60'tdh"]},
    {"canonical_name": "Pentair IntelliFlo i2 2HP", "equipment_type": "pump", "manufacturer": "Pentair", "model_number": "011061", "category": "Variable Speed Pump",
     "specs": {"hp": 2, "gpm_at_60tdh": 109, "voltage": 230}, "aliases": ["intelliflo i2", "intelliflo i2 2hp", "011061"]},
    {"canonical_name": "Pentair IntelliFlo 3", "equipment_type": "pump", "manufacturer": "Pentair", "model_number": "011075", "category": "Variable Speed Pump",
     "specs": {"hp": 3, "voltage": 230}, "aliases": ["intelliflo3", "intelliflo 3", "011075"]},
    {"canonical_name": "Pentair IntelliFlo XF VS", "equipment_type": "pump", "manufacturer": "Pentair", "model_number": "022055", "category": "Variable Speed Pump",
     "specs": {"hp": 5, "gpm_at_60tdh": 158, "voltage": 230}, "aliases": ["intelliflo xf", "xf", "022055", "whisperfloxf-vs 5hp"]},
    {"canonical_name": "Pentair IntelliPro VS+SVRS", "equipment_type": "pump", "manufacturer": "Pentair", "model_number": "011037", "category": "Variable Speed Pump",
     "specs": {"hp": 3, "voltage": 230}, "aliases": ["intellipro", "intellipro vs+svrs", "011037"]},
    {"canonical_name": "Pentair WhisperFlo VST", "equipment_type": "pump", "manufacturer": "Pentair", "model_number": "011533", "category": "Variable Speed Pump",
     "specs": {"hp": 2.6, "gpm_at_60tdh": 112, "voltage": 230}, "aliases": ["whisperflo vst", "011533", "whisperflo vst 011533 2.6hp", "whisperflow vst"]},
    {"canonical_name": "Pentair WhisperFlo", "equipment_type": "pump", "manufacturer": "Pentair", "model_number": "011773", "category": "Single Speed Pump",
     "specs": {"voltage": 230}, "aliases": ["whisperflo", "whisperflow", "wfe"]},
    {"canonical_name": "Pentair WhisperFlo WFE-2 0.5HP", "equipment_type": "pump", "manufacturer": "Pentair", "model_number": "WFE-2", "category": "Single Speed Pump",
     "specs": {"hp": 0.5}, "aliases": ["wfe-2", "wfe2"]},
    {"canonical_name": "Pentair WhisperFlo WFE-3 0.75HP", "equipment_type": "pump", "manufacturer": "Pentair", "model_number": "WFE-3", "category": "Single Speed Pump",
     "specs": {"hp": 0.75}, "aliases": ["wfe-3", "wfe3"]},
    {"canonical_name": "Pentair WhisperFlo WFE-4 1HP", "equipment_type": "pump", "manufacturer": "Pentair", "model_number": "WFE-4", "category": "Single Speed Pump",
     "specs": {"hp": 1}, "aliases": ["wfe-4", "wfe4"]},
    {"canonical_name": "Pentair WhisperFlo WFE-6 1.5HP", "equipment_type": "pump", "manufacturer": "Pentair", "model_number": "WFE-6", "category": "Single Speed Pump",
     "specs": {"hp": 1.5}, "aliases": ["wfe-6", "wfe6", "wfet-6"]},
    {"canonical_name": "Pentair WhisperFlo WFE-8 2HP", "equipment_type": "pump", "manufacturer": "Pentair", "model_number": "WFE-8", "category": "Single Speed Pump",
     "specs": {"hp": 2}, "aliases": ["wfe-8", "wfe8", "-wfe-8"]},
    {"canonical_name": "Pentair WhisperFlo WFE-12 3HP", "equipment_type": "pump", "manufacturer": "Pentair", "model_number": "WFE-12", "category": "Single Speed Pump",
     "specs": {"hp": 3}, "aliases": ["wfe-12", "wfet-12", "wfe-12, 3 hp"]},
    {"canonical_name": "Pentair WhisperFlo WFK-4 1HP", "equipment_type": "pump", "manufacturer": "Pentair", "model_number": "WFK-4", "category": "Single Speed Pump",
     "specs": {"hp": 1}, "aliases": ["wfk-4"]},
    {"canonical_name": "Pentair WhisperFlo WFK-6 1.5HP", "equipment_type": "pump", "manufacturer": "Pentair", "model_number": "WFK-6", "category": "Single Speed Pump",
     "specs": {"hp": 1.5}, "aliases": ["wfk-6"]},
    {"canonical_name": "Pentair WhisperFlo WFK-8 2HP", "equipment_type": "pump", "manufacturer": "Pentair", "model_number": "WFK-8", "category": "Single Speed Pump",
     "specs": {"hp": 2}, "aliases": ["wfk-8"]},
    {"canonical_name": "Pentair WhisperFlo WFK-12 3HP", "equipment_type": "pump", "manufacturer": "Pentair", "model_number": "WFK-12", "category": "Single Speed Pump",
     "specs": {"hp": 3}, "aliases": ["wfk-12"]},
    {"canonical_name": "Pentair WhisperFlo XF 5HP", "equipment_type": "pump", "manufacturer": "Pentair", "model_number": "XFK-20", "category": "Single Speed Pump",
     "specs": {"hp": 5}, "aliases": ["xfk-20", "xf", "whisperfloxf"]},
    {"canonical_name": "Pentair SuperFlo VS", "equipment_type": "pump", "manufacturer": "Pentair", "model_number": "342001", "category": "Variable Speed Pump",
     "specs": {"hp": 1.5, "voltage": 230}, "aliases": ["superflo vs", "superflo", "342001"]},
    {"canonical_name": "Pentair SuperMax VS", "equipment_type": "pump", "manufacturer": "Pentair", "model_number": "343001", "category": "Variable Speed Pump",
     "specs": {"hp": 1.5, "voltage": 230}, "aliases": ["supermax vs", "supermax vs 343001", "343001"]},
    {"canonical_name": "Pentair Challenger", "equipment_type": "pump", "manufacturer": "Pentair", "model_number": "?"  , "category": "Single Speed Pump",
     "specs": {}, "aliases": ["challenger", "pac fab challenger"]},

    # PUMPS — Sta-Rite (Pentair family)
    {"canonical_name": "Sta-Rite Max-E-Pro", "equipment_type": "pump", "manufacturer": "Sta-Rite", "model_number": "P6E6E-206L", "category": "Single Speed Pump",
     "specs": {"hp": 1}, "aliases": ["max-e-pro", "sta-rite max-e-pro", "p6e6e", "p6e6e-206l", "sta-rite p6e6e-206l", "starite max-e-pro"]},
    {"canonical_name": "Sta-Rite Max-E-Pro 1.5HP", "equipment_type": "pump", "manufacturer": "Sta-Rite", "model_number": "P6E6F-207L", "category": "Single Speed Pump",
     "specs": {"hp": 1.5}, "aliases": ["p6e6f-207l", "p6e6f", "sta-rite p6e6f-207l"]},
    {"canonical_name": "Sta-Rite Max-E-Pro 2HP", "equipment_type": "pump", "manufacturer": "Sta-Rite", "model_number": "P6E6D-205L", "category": "Single Speed Pump",
     "specs": {"hp": 2}, "aliases": ["p6e6d-205l", "p6e6d"]},
    {"canonical_name": "Sta-Rite Max-E-Pro 0.75HP", "equipment_type": "pump", "manufacturer": "Sta-Rite", "model_number": "P6E6C-20", "category": "Single Speed Pump",
     "specs": {"hp": 0.75}, "aliases": ["p6e6c-20", "p6e6c"]},

    # PUMPS — Hayward
    {"canonical_name": "Hayward Super Pump VS", "equipment_type": "pump", "manufacturer": "Hayward", "model_number": "SP2600VSP", "category": "Variable Speed Pump",
     "specs": {"hp": 1.65, "voltage": 230}, "aliases": ["super pump vs", "sp2600vsp"]},
    {"canonical_name": "Hayward TriStar VS", "equipment_type": "pump", "manufacturer": "Hayward", "model_number": "SP3200VSP", "category": "Variable Speed Pump",
     "specs": {"hp": 1.85, "voltage": 230}, "aliases": ["tristar vs", "sp3200vsp"]},
    {"canonical_name": "Hayward MaxFlo VS", "equipment_type": "pump", "manufacturer": "Hayward", "model_number": "SP2302VSP", "category": "Variable Speed Pump",
     "specs": {"hp": 1.65, "voltage": 230}, "aliases": ["maxflo vs", "sp2302vsp"]},
    {"canonical_name": "Hayward EcoStar", "equipment_type": "pump", "manufacturer": "Hayward", "model_number": "SP3400VSP", "category": "Variable Speed Pump",
     "specs": {"hp": 3.10, "voltage": 230}, "aliases": ["ecostar", "sp3400vsp"]},
    {"canonical_name": "Hayward Super Pump SP3010EEAZ 1HP", "equipment_type": "pump", "manufacturer": "Hayward", "model_number": "SP3010EEAZ", "category": "Single Speed Pump",
     "specs": {"hp": 1}, "aliases": ["sp3010eeaz", "hayward sp3010eeaz"]},
    {"canonical_name": "Hayward Super Pump SP3020EEAZ 2HP", "equipment_type": "pump", "manufacturer": "Hayward", "model_number": "SP3020EEAZ", "category": "Single Speed Pump",
     "specs": {"hp": 2, "gpm_at_60tdh": 112}, "aliases": ["sp3020eeaz", "hayward sp3020eeaz 2.0 hp"]},
    {"canonical_name": "Hayward SuperFlo", "equipment_type": "pump", "manufacturer": "Hayward", "model_number": "SP2600", "category": "Single Speed Pump",
     "specs": {}, "aliases": ["hayward superflo"]},

    # PUMPS — Jandy / Zodiac
    {"canonical_name": "Jandy FloPro VS", "equipment_type": "pump", "manufacturer": "Jandy", "model_number": "VSSHP270AUT", "category": "Variable Speed Pump",
     "specs": {"hp": 2.7, "voltage": 230}, "aliases": ["flopro vs", "jandy flopro"]},
    {"canonical_name": "Jandy Stealth", "equipment_type": "pump", "manufacturer": "Jandy", "model_number": "SHPM", "category": "Single Speed Pump",
     "specs": {}, "aliases": ["jandy stealth", "stealth"]},

    # PUMPS — Waterway
    {"canonical_name": "Waterway Champion 1.5HP", "equipment_type": "pump", "manufacturer": "Waterway", "model_number": "?"  , "category": "Single Speed Pump",
     "specs": {"hp": 1.5}, "aliases": ["waterway champion", "waterway"]},

    # PUMPS — Aquastar (AquaStar is a brand in Sac County EMD data)
    {"canonical_name": "AquaStar 10AV", "equipment_type": "pump", "manufacturer": "AquaStar", "model_number": "10AV", "category": "Pump",
     "specs": {}, "aliases": ["aquastar 10av", "10av", "10avr"]},

    # ═══════════════════════════════════════════════════════════
    # FILTERS — Pentair
    # ═══════════════════════════════════════════════════════════
    {"canonical_name": "Pentair Clean & Clear Plus 320 sqft", "equipment_type": "filter", "manufacturer": "Pentair", "model_number": "160340", "category": "Cartridge Filter",
     "specs": {"sqft": 320}, "aliases": ["ccp320", "ccp-320", "clean & clear plus 320", "160340", "pentair ccp320"]},
    {"canonical_name": "Pentair Clean & Clear Plus 420 sqft", "equipment_type": "filter", "manufacturer": "Pentair", "model_number": "160301", "category": "Cartridge Filter",
     "specs": {"sqft": 420}, "aliases": ["ccp420", "ccp-420", "clean & clear plus 420", "160301", "pentair ccp420"]},
    {"canonical_name": "Pentair Clean & Clear Plus 520 sqft", "equipment_type": "filter", "manufacturer": "Pentair", "model_number": "160332", "category": "Cartridge Filter",
     "specs": {"sqft": 520}, "aliases": ["ccp520", "ccp-520", "clean & clear plus 520", "160332", "pentair ccp520"]},
    {"canonical_name": "Pentair Clean & Clear Plus 240 sqft", "equipment_type": "filter", "manufacturer": "Pentair", "model_number": "160317", "category": "Cartridge Filter",
     "specs": {"sqft": 240}, "aliases": ["ccp240", "ccp-240", "160317"]},
    {"canonical_name": "Pentair Triton II TR60", "equipment_type": "filter", "manufacturer": "Pentair", "model_number": "TR60", "category": "Sand Filter",
     "specs": {"sqft": 3.14, "gpm": 60}, "aliases": ["triton tr60", "tr60", "tr-60", "triton"]},
    {"canonical_name": "Pentair Triton II TR100", "equipment_type": "filter", "manufacturer": "Pentair", "model_number": "TR100C", "category": "Sand Filter",
     "specs": {"sqft": 4.91, "gpm": 100}, "aliases": ["triton tr100", "tr100", "tr-100", "tr100c"]},
    {"canonical_name": "Pentair Triton II TR140", "equipment_type": "filter", "manufacturer": "Pentair", "model_number": "TR140C", "category": "Sand Filter",
     "specs": {"sqft": 6.93, "gpm": 140}, "aliases": ["triton tr140", "tr140", "tr140c"]},
    {"canonical_name": "Pentair FNS Plus DE 36 sqft", "equipment_type": "filter", "manufacturer": "Pentair", "model_number": "180007", "category": "DE Filter",
     "specs": {"sqft": 36}, "aliases": ["fns plus 36", "de3620", "180007"]},
    {"canonical_name": "Pentair FNS Plus DE 48 sqft", "equipment_type": "filter", "manufacturer": "Pentair", "model_number": "180008", "category": "DE Filter",
     "specs": {"sqft": 48}, "aliases": ["fns plus 48", "de4820", "180008"]},
    {"canonical_name": "Pentair FNS Plus DE 60 sqft", "equipment_type": "filter", "manufacturer": "Pentair", "model_number": "180009", "category": "DE Filter",
     "specs": {"sqft": 60}, "aliases": ["fns plus 60", "de6020", "180009"]},
    {"canonical_name": "Pentair Quad DE 60 sqft", "equipment_type": "filter", "manufacturer": "Pentair", "model_number": "178654", "category": "DE Filter",
     "specs": {"sqft": 60}, "aliases": ["quad de 60", "178654"]},
    {"canonical_name": "Pentair CL580 Cartridge Filter", "equipment_type": "filter", "manufacturer": "Pentair", "model_number": "CL580", "category": "Cartridge Filter",
     "specs": {"sqft": 580}, "aliases": ["cl580"]},

    # FILTERS — Sta-Rite
    {"canonical_name": "Sta-Rite System 3 S7M120", "equipment_type": "filter", "manufacturer": "Sta-Rite", "model_number": "S7M120", "category": "Modular DE/Cartridge Filter",
     "specs": {"sqft": 300}, "aliases": ["s7m120", "system 3 s7m120", "sta-rite s7m120", "sm7", "sys3 s7m120"]},
    {"canonical_name": "Sta-Rite System 3 S8M150", "equipment_type": "filter", "manufacturer": "Sta-Rite", "model_number": "S8M150", "category": "Modular DE/Cartridge Filter",
     "specs": {"sqft": 450}, "aliases": ["s8m150", "system 3 s8m150", "sta-rite s8m150", "starite s8m150"]},

    # FILTERS — Hayward
    {"canonical_name": "Hayward SwimClear C2030", "equipment_type": "filter", "manufacturer": "Hayward", "model_number": "C2030", "category": "Cartridge Filter",
     "specs": {"sqft": 225}, "aliases": ["swimclear c2030", "c2030", "hayward c2030"]},
    {"canonical_name": "Hayward SwimClear C3030", "equipment_type": "filter", "manufacturer": "Hayward", "model_number": "C3030", "category": "Cartridge Filter",
     "specs": {"sqft": 325}, "aliases": ["swimclear c3030", "c3030", "hayward c3030"]},
    {"canonical_name": "Hayward SwimClear C4030", "equipment_type": "filter", "manufacturer": "Hayward", "model_number": "C4030", "category": "Cartridge Filter",
     "specs": {"sqft": 425}, "aliases": ["swimclear c4030", "c4030", "hayward c4030"]},
    {"canonical_name": "Hayward SwimClear C5030", "equipment_type": "filter", "manufacturer": "Hayward", "model_number": "C5030", "category": "Cartridge Filter",
     "specs": {"sqft": 525}, "aliases": ["swimclear c5030", "c5030", "c5020", "hayward c5020"]},
    {"canonical_name": "Hayward StarClear Plus C1200", "equipment_type": "filter", "manufacturer": "Hayward", "model_number": "C1200", "category": "Cartridge Filter",
     "specs": {"sqft": 120}, "aliases": ["starclear plus", "c1200"]},
    {"canonical_name": "Hayward Pro-Grid DE60", "equipment_type": "filter", "manufacturer": "Hayward", "model_number": "DE6020", "category": "DE Filter",
     "specs": {"sqft": 60}, "aliases": ["pro-grid de60", "de6020"]},
    {"canonical_name": "Hayward Pro Series Sand S244T", "equipment_type": "filter", "manufacturer": "Hayward", "model_number": "S244T", "category": "Sand Filter",
     "specs": {"diameter_in": 24}, "aliases": ["pro series sand", "s244t", "hayward sand"]},

    # FILTERS — Waterway
    {"canonical_name": "Waterway Crystal Water DE", "equipment_type": "filter", "manufacturer": "Waterway", "model_number": "57-0525", "category": "DE Filter",
     "specs": {}, "aliases": ["waterway 57-0525", "57-0525", "waterway crystal water"]},

    # FILTERS — Stark
    {"canonical_name": "Stark SS Commercial Filter", "equipment_type": "filter", "manufacturer": "Stark", "model_number": "SS", "category": "Commercial Filter",
     "specs": {}, "aliases": ["stark ss", "stark"]},

    # ═══════════════════════════════════════════════════════════
    # HEATERS
    # ═══════════════════════════════════════════════════════════
    {"canonical_name": "Raypak 206A", "equipment_type": "heater", "manufacturer": "Raypak", "model_number": "206A", "category": "Gas Heater",
     "specs": {"btu": 199500}, "aliases": ["raypak 206a", "206a"]},
    {"canonical_name": "Raypak 266A", "equipment_type": "heater", "manufacturer": "Raypak", "model_number": "266A", "category": "Gas Heater",
     "specs": {"btu": 266000}, "aliases": ["raypak 266a", "266a"]},
    {"canonical_name": "Raypak 336A", "equipment_type": "heater", "manufacturer": "Raypak", "model_number": "336A", "category": "Gas Heater",
     "specs": {"btu": 336000}, "aliases": ["raypak 336a", "336a"]},
    {"canonical_name": "Raypak 406A", "equipment_type": "heater", "manufacturer": "Raypak", "model_number": "406A", "category": "Gas Heater",
     "specs": {"btu": 399000}, "aliases": ["raypak 406a", "406a"]},
    {"canonical_name": "Pentair MasterTemp 200", "equipment_type": "heater", "manufacturer": "Pentair", "model_number": "460730", "category": "Gas Heater",
     "specs": {"btu": 200000}, "aliases": ["mastertemp 200", "460730"]},
    {"canonical_name": "Pentair MasterTemp 250", "equipment_type": "heater", "manufacturer": "Pentair", "model_number": "460731", "category": "Gas Heater",
     "specs": {"btu": 250000}, "aliases": ["mastertemp 250", "460731"]},
    {"canonical_name": "Pentair MasterTemp 300", "equipment_type": "heater", "manufacturer": "Pentair", "model_number": "460732", "category": "Gas Heater",
     "specs": {"btu": 300000}, "aliases": ["mastertemp 300", "460732"]},
    {"canonical_name": "Pentair MasterTemp 400", "equipment_type": "heater", "manufacturer": "Pentair", "model_number": "460736", "category": "Gas Heater",
     "specs": {"btu": 400000}, "aliases": ["mastertemp 400", "460736"]},
    {"canonical_name": "Pentair Max-E-Therm 200", "equipment_type": "heater", "manufacturer": "Pentair", "model_number": "461059", "category": "Gas Heater",
     "specs": {"btu": 200000}, "aliases": ["max-e-therm 200", "461059"]},
    {"canonical_name": "Pentair Max-E-Therm 400", "equipment_type": "heater", "manufacturer": "Pentair", "model_number": "461060", "category": "Gas Heater",
     "specs": {"btu": 400000}, "aliases": ["max-e-therm 400", "461060"]},
    {"canonical_name": "Pentair UltraTemp 120", "equipment_type": "heater", "manufacturer": "Pentair", "model_number": "460933", "category": "Heat Pump",
     "specs": {"btu": 125000}, "aliases": ["ultratemp 120", "460933"]},
    {"canonical_name": "Hayward Universal H-Series 250", "equipment_type": "heater", "manufacturer": "Hayward", "model_number": "H250FDN", "category": "Gas Heater",
     "specs": {"btu": 250000}, "aliases": ["h-series 250", "h250fdn"]},
    {"canonical_name": "Hayward Universal H-Series 400", "equipment_type": "heater", "manufacturer": "Hayward", "model_number": "H400FDN", "category": "Gas Heater",
     "specs": {"btu": 400000}, "aliases": ["h-series 400", "h400fdn"]},
    {"canonical_name": "Hayward HeatPro", "equipment_type": "heater", "manufacturer": "Hayward", "model_number": "HP21404T", "category": "Heat Pump",
     "specs": {"btu": 140000}, "aliases": ["heatpro", "hp21404t"]},
    {"canonical_name": "Jandy JXi 400", "equipment_type": "heater", "manufacturer": "Jandy", "model_number": "JXi400N", "category": "Gas Heater",
     "specs": {"btu": 400000}, "aliases": ["jxi 400", "jxi400n"]},
    {"canonical_name": "Raypak CrossWind Heat Pump", "equipment_type": "heater", "manufacturer": "Raypak", "model_number": "R5450ti", "category": "Heat Pump",
     "specs": {"btu": 119000}, "aliases": ["crosswind", "r5450ti"]},

    # ═══════════════════════════════════════════════════════════
    # CHLORINATORS / CHEMICAL FEED
    # ═══════════════════════════════════════════════════════════
    {"canonical_name": "RolaChem RC 103SC", "equipment_type": "chlorinator", "manufacturer": "RolaChem", "model_number": "RC103SC", "category": "Salt Chlorine Generator",
     "specs": {}, "aliases": ["rc103sc", "rolachem rc103sc", "rolachem rc 103sc", "rc-103sc"]},
    {"canonical_name": "RolaChem RC25/53S Liquid Feed", "equipment_type": "chemical_feeder", "manufacturer": "RolaChem", "model_number": "RC25/53S", "category": "Liquid Chemical Feeder",
     "specs": {}, "aliases": ["rc25/53s", "rc-25/53 sc", "rc-25/53", "rolachem rc25/53s", "rolachem rc25/53s (liq)", "300-29x"]},
    {"canonical_name": "RolaChem RC-103 SP", "equipment_type": "chlorinator", "manufacturer": "RolaChem", "model_number": "RC-103 SP", "category": "Chemical Controller",
     "specs": {}, "aliases": ["rc-103 sp", "rc103sp"]},
    {"canonical_name": "Pentair IntelliChlor IC20", "equipment_type": "chlorinator", "manufacturer": "Pentair", "model_number": "520554", "category": "Salt Chlorine Generator",
     "specs": {"max_gallons": 20000}, "aliases": ["intellichlor ic20", "ic20", "520554"]},
    {"canonical_name": "Pentair IntelliChlor IC40", "equipment_type": "chlorinator", "manufacturer": "Pentair", "model_number": "520555", "category": "Salt Chlorine Generator",
     "specs": {"max_gallons": 40000}, "aliases": ["intellichlor ic40", "ic40", "520555"]},
    {"canonical_name": "Pentair IntelliChlor IC60", "equipment_type": "chlorinator", "manufacturer": "Pentair", "model_number": "520556", "category": "Salt Chlorine Generator",
     "specs": {"max_gallons": 60000}, "aliases": ["intellichlor ic60", "ic60", "520556"]},
    {"canonical_name": "Hayward AquaRite", "equipment_type": "chlorinator", "manufacturer": "Hayward", "model_number": "AQR15", "category": "Salt Chlorine Generator",
     "specs": {"max_gallons": 40000}, "aliases": ["aquarite", "aqr15", "hayward aquarite"]},
    {"canonical_name": "Hayward AquaRite Pro", "equipment_type": "chlorinator", "manufacturer": "Hayward", "model_number": "AQR-PRO", "category": "Salt Chlorine Generator",
     "specs": {"max_gallons": 40000}, "aliases": ["aquarite pro", "aqr-pro"]},
    {"canonical_name": "Jandy AquaPure Ei", "equipment_type": "chlorinator", "manufacturer": "Jandy", "model_number": "APURE35", "category": "Salt Chlorine Generator",
     "specs": {"max_gallons": 35000}, "aliases": ["aquapure", "aquapure ei", "apure35"]},

    # ═══════════════════════════════════════════════════════════
    # AUTOMATION
    # ═══════════════════════════════════════════════════════════
    {"canonical_name": "Pentair IntelliCenter", "equipment_type": "automation", "manufacturer": "Pentair", "model_number": "522036", "category": "Pool Automation",
     "specs": {}, "aliases": ["intellicenter", "522036"]},
    {"canonical_name": "Pentair EasyTouch", "equipment_type": "automation", "manufacturer": "Pentair", "model_number": "520593", "category": "Pool Automation",
     "specs": {}, "aliases": ["easytouch", "520593"]},
    {"canonical_name": "Pentair ScreenLogic", "equipment_type": "automation", "manufacturer": "Pentair", "model_number": "522104", "category": "Pool Automation",
     "specs": {}, "aliases": ["screenlogic", "522104"]},
    {"canonical_name": "Pentair IntelliConnect", "equipment_type": "automation", "manufacturer": "Pentair", "model_number": "523317", "category": "Pool Automation",
     "specs": {}, "aliases": ["intelliconnect", "523317"]},
    {"canonical_name": "Hayward OmniLogic", "equipment_type": "automation", "manufacturer": "Hayward", "model_number": "?"  , "category": "Pool Automation",
     "specs": {}, "aliases": ["omnilogic"]},
    {"canonical_name": "Hayward ProLogic", "equipment_type": "automation", "manufacturer": "Hayward", "model_number": "PL-P-4", "category": "Pool Automation",
     "specs": {}, "aliases": ["prologic", "pl-p-4"]},
    {"canonical_name": "Hayward AquaPlus", "equipment_type": "automation", "manufacturer": "Hayward", "model_number": "PL-PLUS", "category": "Pool Automation",
     "specs": {}, "aliases": ["aquaplus", "pl-plus"]},
    {"canonical_name": "Jandy AquaLink RS", "equipment_type": "automation", "manufacturer": "Jandy", "model_number": "RS-PS8", "category": "Pool Automation",
     "specs": {}, "aliases": ["aqualink", "aqualink rs", "rs-ps8"]},
    {"canonical_name": "Jandy iAquaLink", "equipment_type": "automation", "manufacturer": "Jandy", "model_number": "IQ904-PS", "category": "Pool Automation",
     "specs": {}, "aliases": ["iaqualink", "iq904"]},

    # ═══════════════════════════════════════════════════════════
    # BOOSTER PUMPS
    # ═══════════════════════════════════════════════════════════
    {"canonical_name": "Polaris PB4-60 Booster Pump", "equipment_type": "booster_pump", "manufacturer": "Polaris", "model_number": "PB4-60", "category": "Booster Pump",
     "specs": {"hp": 0.75}, "aliases": ["pb4-60", "polaris booster", "polaris pb4-60"]},
    {"canonical_name": "Pentair Letro LA01N Booster Pump", "equipment_type": "booster_pump", "manufacturer": "Pentair", "model_number": "LA01N", "category": "Booster Pump",
     "specs": {"hp": 0.75}, "aliases": ["la01n", "letro booster"]},

    # ═══════════════════════════════════════════════════════════
    # UV / OZONE SANITIZERS (from EMD data)
    # ═══════════════════════════════════════════════════════════
    {"canonical_name": "UV Sanitizer System", "equipment_type": "chemical_feeder", "manufacturer": None, "model_number": None, "category": "UV Sanitizer",
     "specs": {}, "aliases": ["uv"]},

    # ═══════════════════════════════════════════════════════════
    # SVRS / SAFETY (from EMD data)
    # ═══════════════════════════════════════════════════════════
    {"canonical_name": "Emotron PSP 20 SVRS", "equipment_type": "automation", "manufacturer": "Emotron", "model_number": "PSP 20", "category": "SVRS Controller",
     "specs": {}, "aliases": ["emotron psp 20", "emotron psp20"]},

    # ═══════════════════════════════════════════════════════════
    # DRAINS (common in EMD inspections)
    # ═══════════════════════════════════════════════════════════
    {"canonical_name": "Pentair StarGuard Main Drain", "equipment_type": "equipment", "manufacturer": "Pentair", "model_number": "500100", "category": "Main Drain Cover",
     "specs": {}, "aliases": ["starguard", "500100"]},
    {"canonical_name": "AquaStar Main Drain", "equipment_type": "equipment", "manufacturer": "AquaStar", "model_number": None, "category": "Main Drain Cover",
     "specs": {}, "aliases": ["aquastar drain", "aquastar main drain"]},
]


async def seed():
    async with get_db_context() as db:
        created = 0
        skipped = 0
        for item in CATALOG:
            # Check if already exists by manufacturer + canonical_name
            existing = await db.execute(
                select(EquipmentCatalog).where(
                    EquipmentCatalog.canonical_name == item["canonical_name"]
                ).limit(1)
            )
            if existing.scalar_one_or_none():
                skipped += 1
                continue

            entry = EquipmentCatalog(
                id=str(uuid.uuid4()),
                canonical_name=item["canonical_name"],
                equipment_type=item["equipment_type"],
                manufacturer=item.get("manufacturer"),
                model_number=item.get("model_number"),
                category=item.get("category"),
                specs=item.get("specs"),
                aliases=item.get("aliases", []),
                is_common=True,
                source="seed",
            )
            db.add(entry)
            created += 1

        await db.commit()
        print(f"Equipment Catalog Seed: {created} created, {skipped} skipped (already exist)")
        print(f"Total entries: {created + skipped}")


if __name__ == "__main__":
    asyncio.run(seed())
