"""Seed catalog — common pool parts for SCP/Pool360 catalog.

Populates parts_catalog with ~100 commonly-used pool industry parts.
All entries use vendor_provider="scp" and realistic SKUs/brands.
"""

import uuid
import logging
from datetime import datetime, timezone

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.parts_catalog import PartsCatalog

logger = logging.getLogger(__name__)

SEED_PARTS = [
    # === Pumps ===
    {"sku": "011018", "name": "WhisperFlo 1.5HP Pool Pump", "brand": "Pentair", "category": "Pumps", "subcategory": "Single Speed", "description": "High-performance single-speed pool pump, 1.5 HP, 208-230V", "is_chemical": False},
    {"sku": "011028", "name": "WhisperFlo 2HP Pool Pump", "brand": "Pentair", "category": "Pumps", "subcategory": "Single Speed", "description": "High-performance single-speed pool pump, 2 HP, 208-230V", "is_chemical": False},
    {"sku": "342001", "name": "SuperFlo VS Variable Speed Pump", "brand": "Pentair", "category": "Pumps", "subcategory": "Variable Speed", "description": "Variable speed pool pump, energy efficient, 1.5 HP", "is_chemical": False},
    {"sku": "EC-942006", "name": "Super Pump VS 700", "brand": "Hayward", "category": "Pumps", "subcategory": "Variable Speed", "description": "Variable speed pump with built-in timer, 700 RPM to 3450 RPM", "is_chemical": False},
    {"sku": "SP2610X15", "name": "Super Pump 1.5HP", "brand": "Hayward", "category": "Pumps", "subcategory": "Single Speed", "description": "Single speed super pump, 1.5 HP, heavy-duty motor", "is_chemical": False},
    {"sku": "SP2615X20", "name": "Super Pump 2HP", "brand": "Hayward", "category": "Pumps", "subcategory": "Single Speed", "description": "Single speed super pump, 2 HP, heavy-duty motor", "is_chemical": False},
    {"sku": "EC-34520VS", "name": "IntelliFlo VSF Variable Speed Flow Pump", "brand": "Pentair", "category": "Pumps", "subcategory": "Variable Speed", "description": "Variable speed and flow pump with built-in diagnostics, 3 HP", "is_chemical": False},
    {"sku": "SP3400VSP", "name": "EcoStar Variable Speed Pump", "brand": "Hayward", "category": "Pumps", "subcategory": "Variable Speed", "description": "Ultra-efficient variable speed pump, Energy Star certified", "is_chemical": False},
    {"sku": "P6RA6E-205L", "name": "Max-Flo XL 1.5HP Pump", "brand": "Pentair", "category": "Pumps", "subcategory": "Single Speed", "description": "Medium-head pump for residential pools, 1.5 HP", "is_chemical": False},

    # === Filters ===
    {"sku": "160316", "name": "Clean & Clear Plus 420 Cartridge Filter", "brand": "Pentair", "category": "Filters", "subcategory": "Cartridge", "description": "420 sq ft cartridge filter for pools up to 42,000 gallons", "is_chemical": False},
    {"sku": "160340", "name": "Clean & Clear Plus 520 Cartridge Filter", "brand": "Pentair", "category": "Filters", "subcategory": "Cartridge", "description": "520 sq ft cartridge filter for pools up to 52,000 gallons", "is_chemical": False},
    {"sku": "EC-160332", "name": "FNS Plus 60 DE Filter", "brand": "Pentair", "category": "Filters", "subcategory": "DE", "description": "60 sq ft DE filter for residential and commercial pools", "is_chemical": False},
    {"sku": "S310T2", "name": "Pro Series 30\" Sand Filter", "brand": "Hayward", "category": "Filters", "subcategory": "Sand", "description": "30-inch sand filter with top-mount valve for pools up to 53,000 gal", "is_chemical": False},
    {"sku": "S244T2", "name": "Pro Series 24\" Sand Filter", "brand": "Hayward", "category": "Filters", "subcategory": "Sand", "description": "24-inch sand filter with top-mount valve for pools up to 33,000 gal", "is_chemical": False},
    {"sku": "C9002", "name": "SwimClear C9002 Cartridge Filter", "brand": "Hayward", "category": "Filters", "subcategory": "Cartridge", "description": "900 sq ft cartridge filter for large residential/commercial pools", "is_chemical": False},
    {"sku": "EC-C17502", "name": "StarClear Plus C1750 Cartridge Filter", "brand": "Hayward", "category": "Filters", "subcategory": "Cartridge", "description": "175 sq ft cartridge filter for pools up to 21,000 gallons", "is_chemical": False},
    {"sku": "178580", "name": "Triton II TR100 Sand Filter", "brand": "Pentair", "category": "Filters", "subcategory": "Sand", "description": "30-inch side-mount sand filter, commercial grade", "is_chemical": False},

    # === Filter Cartridges (replacement) ===
    {"sku": "R173476", "name": "Clean & Clear Plus 420 Replacement Cartridge", "brand": "Pentair", "category": "Filters", "subcategory": "Replacement Cartridges", "description": "Replacement cartridge for CCP420, 4-pack", "is_chemical": False},
    {"sku": "CX1750RE", "name": "StarClear Plus Replacement Cartridge", "brand": "Hayward", "category": "Filters", "subcategory": "Replacement Cartridges", "description": "Replacement cartridge for C1750 filter", "is_chemical": False},
    {"sku": "CX900RE", "name": "Star-Clear II Replacement Cartridge", "brand": "Hayward", "category": "Filters", "subcategory": "Replacement Cartridges", "description": "Replacement cartridge for C900 filter", "is_chemical": False},

    # === Heaters ===
    {"sku": "460736", "name": "MasterTemp 400K BTU Gas Heater", "brand": "Pentair", "category": "Heaters", "subcategory": "Gas", "description": "400,000 BTU natural gas pool heater with digital display", "is_chemical": False},
    {"sku": "460737", "name": "MasterTemp 400K BTU LP Heater", "brand": "Pentair", "category": "Heaters", "subcategory": "Gas", "description": "400,000 BTU propane pool heater with digital display", "is_chemical": False},
    {"sku": "460733", "name": "MasterTemp 250K BTU Gas Heater", "brand": "Pentair", "category": "Heaters", "subcategory": "Gas", "description": "250,000 BTU natural gas pool heater", "is_chemical": False},
    {"sku": "H400FDN", "name": "Universal H-Series 400K BTU Gas Heater", "brand": "Hayward", "category": "Heaters", "subcategory": "Gas", "description": "400,000 BTU natural gas heater with low NOx emissions", "is_chemical": False},
    {"sku": "H250FDN", "name": "Universal H-Series 250K BTU Gas Heater", "brand": "Hayward", "category": "Heaters", "subcategory": "Gas", "description": "250,000 BTU natural gas heater with low NOx emissions", "is_chemical": False},
    {"sku": "HP21404T", "name": "HeatPro Heat Pump", "brand": "Hayward", "category": "Heaters", "subcategory": "Heat Pump", "description": "140,000 BTU heat pump for pools up to 40,000 gallons", "is_chemical": False},
    {"sku": "460962", "name": "UltraTemp 140K BTU Heat Pump", "brand": "Pentair", "category": "Heaters", "subcategory": "Heat Pump", "description": "140,000 BTU heat pump, high efficiency, titanium heat exchanger", "is_chemical": False},

    # === Salt Chlorine Generators ===
    {"sku": "521105", "name": "IntelliChlor IC40 Salt Cell", "brand": "Pentair", "category": "Salt Systems", "subcategory": "Salt Cells", "description": "Salt chlorine generator cell for pools up to 40,000 gallons", "is_chemical": False},
    {"sku": "521104", "name": "IntelliChlor IC20 Salt Cell", "brand": "Pentair", "category": "Salt Systems", "subcategory": "Salt Cells", "description": "Salt chlorine generator cell for pools up to 20,000 gallons", "is_chemical": False},
    {"sku": "W3T-CELL-15", "name": "TurboCell T-Cell-15", "brand": "Hayward", "category": "Salt Systems", "subcategory": "Salt Cells", "description": "Replacement salt cell for AquaRite, pools up to 40,000 gallons", "is_chemical": False},
    {"sku": "W3AQR15", "name": "AquaRite Salt System", "brand": "Hayward", "category": "Salt Systems", "subcategory": "Complete Systems", "description": "Complete salt chlorination system for pools up to 40,000 gallons", "is_chemical": False},
    {"sku": "W3AQR9", "name": "AquaRite Salt System (25K)", "brand": "Hayward", "category": "Salt Systems", "subcategory": "Complete Systems", "description": "Complete salt chlorination system for pools up to 25,000 gallons", "is_chemical": False},

    # === Automation ===
    {"sku": "522104", "name": "IntelliTouch i10+3S System", "brand": "Pentair", "category": "Automation", "subcategory": "Control Systems", "description": "Pool/spa automation with 10 auxiliary circuits and salt chlorinator", "is_chemical": False},
    {"sku": "522105", "name": "EasyTouch 8 Control System", "brand": "Pentair", "category": "Automation", "subcategory": "Control Systems", "description": "Pool/spa automation with 8 auxiliary circuits", "is_chemical": False},
    {"sku": "AQL2-POL-HP", "name": "OmniLogic Pool Control", "brand": "Hayward", "category": "Automation", "subcategory": "Control Systems", "description": "Smart pool/spa automation with app control and voice integration", "is_chemical": False},
    {"sku": "522620", "name": "ScreenLogic2 Interface", "brand": "Pentair", "category": "Automation", "subcategory": "Interfaces", "description": "Wi-Fi interface for IntelliTouch/EasyTouch remote control", "is_chemical": False},

    # === Cleaners ===
    {"sku": "360228", "name": "Polaris Vac-Sweep 360", "brand": "Polaris", "category": "Cleaners", "subcategory": "Pressure Side", "description": "Pressure-side pool cleaner, operates on dedicated booster pump", "is_chemical": False},
    {"sku": "F5B", "name": "Polaris Vac-Sweep 280 BlackMax", "brand": "Polaris", "category": "Cleaners", "subcategory": "Pressure Side", "description": "Pressure-side pool cleaner, operates on existing pump", "is_chemical": False},
    {"sku": "W3PVS40VST", "name": "Polaris Vac-Sweep 3900 Sport", "brand": "Polaris", "category": "Cleaners", "subcategory": "Pressure Side", "description": "Premium pressure-side cleaner with PosiDrive system", "is_chemical": False},
    {"sku": "RC9950CUB", "name": "TigerShark QC Robotic Cleaner", "brand": "Hayward", "category": "Cleaners", "subcategory": "Robotic", "description": "Robotic pool cleaner with quick clean cycle, for pools up to 20x40", "is_chemical": False},
    {"sku": "W3925ADC", "name": "PoolVac XL Suction Cleaner", "brand": "Hayward", "category": "Cleaners", "subcategory": "Suction Side", "description": "Suction-side pool cleaner with AquaPilot steering", "is_chemical": False},
    {"sku": "CNX30", "name": "Navigator Pro Suction Cleaner", "brand": "Hayward", "category": "Cleaners", "subcategory": "Suction Side", "description": "Premium suction-side cleaner with SmartDrive navigation", "is_chemical": False},

    # === Valves ===
    {"sku": "263037", "name": "2\" CPVC Diverter Valve", "brand": "Pentair", "category": "Valves", "subcategory": "Diverter", "description": "2-inch 3-way CPVC diverter valve for pool/spa", "is_chemical": False},
    {"sku": "263038", "name": "2.5\" CPVC Diverter Valve", "brand": "Pentair", "category": "Valves", "subcategory": "Diverter", "description": "2.5-inch 3-way CPVC diverter valve", "is_chemical": False},
    {"sku": "263064", "name": "IntelliValve 2\" Actuator Valve", "brand": "Pentair", "category": "Valves", "subcategory": "Actuator", "description": "24V actuator valve for automation systems, 2-inch", "is_chemical": False},
    {"sku": "SP0715ALL", "name": "Multiport Valve 2\"", "brand": "Hayward", "category": "Valves", "subcategory": "Multiport", "description": "2-inch top-mount multiport valve, 7 positions", "is_chemical": False},
    {"sku": "SP0740DE", "name": "Push-Pull Slide Valve 2\"", "brand": "Hayward", "category": "Valves", "subcategory": "Slide", "description": "2-inch push-pull valve for DE filters", "is_chemical": False},

    # === Motors ===
    {"sku": "354824S", "name": "WhisperFlo 1.5HP Replacement Motor", "brand": "Pentair", "category": "Motors", "subcategory": "Replacement", "description": "Square flange replacement motor for WhisperFlo 1.5HP pump", "is_chemical": False},
    {"sku": "354828S", "name": "WhisperFlo 2HP Replacement Motor", "brand": "Pentair", "category": "Motors", "subcategory": "Replacement", "description": "Square flange replacement motor for WhisperFlo 2HP pump", "is_chemical": False},
    {"sku": "SPX1610Z1M", "name": "Super Pump 1.5HP Motor", "brand": "Hayward", "category": "Motors", "subcategory": "Replacement", "description": "Threaded shaft replacement motor for Super Pump 1.5HP", "is_chemical": False},
    {"sku": "B2854", "name": "2HP Pool Motor 56Y Frame", "brand": "Century", "category": "Motors", "subcategory": "Replacement", "description": "56Y frame, 2HP, 230V, threaded shaft pool motor", "is_chemical": False},
    {"sku": "B2853", "name": "1HP Pool Motor 56Y Frame", "brand": "Century", "category": "Motors", "subcategory": "Replacement", "description": "56Y frame, 1HP, 115/230V, threaded shaft pool motor", "is_chemical": False},
    {"sku": "B2748", "name": "1.5HP Booster Pump Motor", "brand": "Century", "category": "Motors", "subcategory": "Booster", "description": "48Y frame motor for Polaris booster pumps, 115/230V", "is_chemical": False},

    # === Chemicals ===
    {"sku": "23401", "name": "Liquid Chlorine 12.5% - 4x1 Gal", "brand": "Pool Essentials", "category": "Chemicals", "subcategory": "Chlorine", "description": "Sodium hypochlorite 12.5%, case of 4 gallons", "is_chemical": True},
    {"sku": "22201", "name": "Cal-Hypo Shock 73% - 24x1 lb", "brand": "Pool Essentials", "category": "Chemicals", "subcategory": "Shock", "description": "Calcium hypochlorite shock, 73%, case of 24 x 1 lb bags", "is_chemical": True},
    {"sku": "C002508-CS20P4", "name": "3\" Chlorine Tabs 50 lb Bucket", "brand": "Pool Essentials", "category": "Chemicals", "subcategory": "Chlorine", "description": "Trichlor 3-inch stabilized chlorine tablets, 50 lb pail", "is_chemical": True},
    {"sku": "23501", "name": "Muriatic Acid - 4x1 Gal", "brand": "Pool Essentials", "category": "Chemicals", "subcategory": "pH Adjustment", "description": "Hydrochloric acid 31.45%, case of 4 gallons. pH reducer.", "is_chemical": True},
    {"sku": "25201", "name": "Soda Ash (pH Up) - 25 lb", "brand": "Pool Essentials", "category": "Chemicals", "subcategory": "pH Adjustment", "description": "Sodium carbonate, pH increaser, 25 lb bag", "is_chemical": True},
    {"sku": "25101", "name": "Sodium Bicarbonate (Alkalinity Up) - 25 lb", "brand": "Pool Essentials", "category": "Chemicals", "subcategory": "Alkalinity", "description": "Alkalinity increaser, 25 lb bag", "is_chemical": True},
    {"sku": "26201", "name": "Cyanuric Acid (Stabilizer) - 25 lb", "brand": "Pool Essentials", "category": "Chemicals", "subcategory": "Stabilizer", "description": "Conditioner/stabilizer, protects chlorine from UV degradation", "is_chemical": True},
    {"sku": "24101", "name": "Calcium Chloride (Hardness Up) - 25 lb", "brand": "Pool Essentials", "category": "Chemicals", "subcategory": "Calcium", "description": "Calcium hardness increaser, 77%, 25 lb bag", "is_chemical": True},
    {"sku": "C003672-CS78B1", "name": "Potassium Monopersulfate (MPS) Non-Chlorine Shock - 25 lb", "brand": "Pool Essentials", "category": "Chemicals", "subcategory": "Shock", "description": "Non-chlorine oxidizer shock, 25 lb bag", "is_chemical": True},
    {"sku": "27101", "name": "Diatomaceous Earth (DE) - 25 lb", "brand": "Pool Essentials", "category": "Chemicals", "subcategory": "Filter Media", "description": "DE filter powder, 25 lb bag", "is_chemical": True},
    {"sku": "C002518-PL50P1", "name": "Pool Salt - 40 lb Bag", "brand": "Pool Essentials", "category": "Chemicals", "subcategory": "Salt", "description": "High purity pool-grade salt for salt chlorine generators", "is_chemical": True},
    {"sku": "C005075-CS105Q", "name": "Algaecide 60% - 1 Qt", "brand": "Pool Essentials", "category": "Chemicals", "subcategory": "Algaecide", "description": "Concentrated polyquat algaecide, non-foaming, 1 quart", "is_chemical": True},

    # === Lighting ===
    {"sku": "601000", "name": "IntelliBrite 5G LED Color Light", "brand": "Pentair", "category": "Lighting", "subcategory": "LED Pool Lights", "description": "Color LED pool light, 120V, 50ft cord, for new/replacement", "is_chemical": False},
    {"sku": "601011", "name": "MicroBrite Color LED Light", "brand": "Pentair", "category": "Lighting", "subcategory": "LED Pool Lights", "description": "Compact LED color light for spas and small pools, 12V", "is_chemical": False},
    {"sku": "SP0527SLED100", "name": "ColorLogic 4.0 LED Pool Light", "brand": "Hayward", "category": "Lighting", "subcategory": "LED Pool Lights", "description": "LED color pool light, 120V, 100ft cord, 10 fixed colors", "is_chemical": False},
    {"sku": "SP0535LED100", "name": "CrystaLogic LED White Light", "brand": "Hayward", "category": "Lighting", "subcategory": "LED Pool Lights", "description": "White LED pool light, 120V, 100ft cord", "is_chemical": False},

    # === Accessories / Parts ===
    {"sku": "R172009", "name": "Rainbow 320 Chlorinator", "brand": "Pentair", "category": "Accessories", "subcategory": "Chlorinators", "description": "Offline chlorinator, holds up to 9 lbs of 3\" tabs", "is_chemical": False},
    {"sku": "CL200", "name": "In-Line Chlorinator CL200", "brand": "Hayward", "category": "Accessories", "subcategory": "Chlorinators", "description": "In-line automatic chlorinator for above/in-ground pools", "is_chemical": False},
    {"sku": "SP1091LX", "name": "Hayward SP1091LX Skim Vac", "brand": "Hayward", "category": "Accessories", "subcategory": "Skimmers", "description": "Skimmer vacuum plate for wide-mouth skimmers", "is_chemical": False},
    {"sku": "R0557005", "name": "Jandy CV/CL Cartridge (Set of 4)", "brand": "Jandy", "category": "Filters", "subcategory": "Replacement Cartridges", "description": "Replacement cartridge set for Jandy CV/CL 460 filters", "is_chemical": False},
    {"sku": "075140", "name": "Leaf Canister In-Line", "brand": "Pentair", "category": "Accessories", "subcategory": "Cleaners", "description": "In-line leaf canister for pressure-side cleaners", "is_chemical": False},
    {"sku": "R0358800", "name": "Heat Exchanger Assembly", "brand": "Jandy", "category": "Heaters", "subcategory": "Repair Parts", "description": "Replacement heat exchanger for Jandy LXi heater", "is_chemical": False},

    # === O-Rings & Gaskets ===
    {"sku": "071426", "name": "Clean & Clear Plus Tank O-Ring", "brand": "Pentair", "category": "Parts", "subcategory": "O-Rings", "description": "Tank body O-ring for Clean & Clear Plus filters", "is_chemical": False},
    {"sku": "U9-375", "name": "Pump Lid O-Ring (SuperFlo/WhisperFlo)", "brand": "Pentair", "category": "Parts", "subcategory": "O-Rings", "description": "Replacement lid O-ring for SuperFlo and WhisperFlo pumps", "is_chemical": False},
    {"sku": "SX200Z2", "name": "Pro Series Sand Filter O-Ring", "brand": "Hayward", "category": "Parts", "subcategory": "O-Rings", "description": "Drain cap O-ring for Pro Series sand filters", "is_chemical": False},
    {"sku": "SPX1600R", "name": "Super Pump Strainer Cover O-Ring", "brand": "Hayward", "category": "Parts", "subcategory": "O-Rings", "description": "Strainer cover O-ring for Hayward Super Pump", "is_chemical": False},
    {"sku": "SPX0710XZ2", "name": "Multiport Key Cover O-Ring (2-pack)", "brand": "Hayward", "category": "Parts", "subcategory": "O-Rings", "description": "Key cover and knob O-ring for Hayward multiport valves, 2-pack", "is_chemical": False},

    # === Pump Baskets ===
    {"sku": "SPX1600M", "name": "Super Pump Strainer Basket", "brand": "Hayward", "category": "Parts", "subcategory": "Baskets", "description": "Replacement strainer basket for Hayward Super Pump", "is_chemical": False},
    {"sku": "070387", "name": "WhisperFlo Strainer Basket", "brand": "Pentair", "category": "Parts", "subcategory": "Baskets", "description": "Replacement strainer basket for WhisperFlo pump", "is_chemical": False},
    {"sku": "SPX3200M", "name": "TriStar/EcoStar Strainer Basket", "brand": "Hayward", "category": "Parts", "subcategory": "Baskets", "description": "Replacement strainer basket for TriStar and EcoStar pumps", "is_chemical": False},

    # === Skimmer Baskets & Parts ===
    {"sku": "SPX1082CA", "name": "Skimmer Basket SP1082", "brand": "Hayward", "category": "Parts", "subcategory": "Baskets", "description": "Replacement skimmer basket for Hayward SP1082/1083/1084 skimmers", "is_chemical": False},
    {"sku": "SPX1070C", "name": "Skimmer Basket SP1070", "brand": "Hayward", "category": "Parts", "subcategory": "Baskets", "description": "Replacement skimmer basket for Hayward SP1070 automatic skimmers", "is_chemical": False},
    {"sku": "08650-0007", "name": "Admiral Skimmer Basket", "brand": "Pentair", "category": "Parts", "subcategory": "Baskets", "description": "Replacement basket for Pentair Admiral skimmers", "is_chemical": False},

    # === Pressure Gauges & Misc ===
    {"sku": "190059", "name": "1/4\" Bottom-Mount Pressure Gauge", "brand": "Pentair", "category": "Parts", "subcategory": "Gauges", "description": "0-60 PSI pressure gauge, 1/4\" NPT bottom mount", "is_chemical": False},
    {"sku": "ECX1796", "name": "1/4\" Back-Mount Pressure Gauge", "brand": "Hayward", "category": "Parts", "subcategory": "Gauges", "description": "0-60 PSI pressure gauge for Hayward filters", "is_chemical": False},

    # === Test Kits ===
    {"sku": "K-2006", "name": "FAS-DPD Test Kit", "brand": "Taylor", "category": "Testing", "subcategory": "Test Kits", "description": "Complete FAS-DPD chlorine test kit with CYA, pH, TA, CH", "is_chemical": False},
    {"sku": "K-2005", "name": "Complete Pool Test Kit", "brand": "Taylor", "category": "Testing", "subcategory": "Test Kits", "description": "Basic pool test kit: free/total chlorine, pH, TA, CH", "is_chemical": False},
    {"sku": "R-0871-C", "name": "FAS-DPD Titrating Reagent (2 oz)", "brand": "Taylor", "category": "Testing", "subcategory": "Reagents", "description": "Chlorine titrating reagent for FAS-DPD test, 2 oz bottle", "is_chemical": False},
    {"sku": "R-0013-C", "name": "Cyanuric Acid Reagent (2 oz)", "brand": "Taylor", "category": "Testing", "subcategory": "Reagents", "description": "CYA test reagent, 2 oz bottle", "is_chemical": False},

    # === Pool Tools ===
    {"sku": "R111358", "name": "Professional Leaf Rake", "brand": "Pentair", "category": "Tools", "subcategory": "Nets", "description": "Heavy-duty deep-bag leaf rake with aluminum frame", "is_chemical": False},
    {"sku": "8040", "name": "Telepole 16ft (2-section)", "brand": "Pentair", "category": "Tools", "subcategory": "Poles", "description": "16-foot 2-section anodized aluminum telepole", "is_chemical": False},
    {"sku": "R201386", "name": "18\" Curved Wall Brush", "brand": "Pentair", "category": "Tools", "subcategory": "Brushes", "description": "18-inch curved pool wall brush with stainless steel bristles", "is_chemical": False},
    {"sku": "R201296", "name": "18\" Algae Brush", "brand": "Pentair", "category": "Tools", "subcategory": "Brushes", "description": "18-inch algae brush with stainless steel bristles", "is_chemical": False},
    {"sku": "R111556", "name": "Weighted Flex Vacuum Head 14\"", "brand": "Pentair", "category": "Tools", "subcategory": "Vacuum Heads", "description": "14-inch weighted flexible vacuum head for gunite pools", "is_chemical": False},
    {"sku": "SP1106", "name": "1.5\" x 50ft Vacuum Hose", "brand": "Hayward", "category": "Tools", "subcategory": "Hoses", "description": "1.5-inch x 50-foot pool vacuum hose with swivel cuff", "is_chemical": False},
]


async def seed_catalog(db: AsyncSession) -> dict:
    """Seed parts_catalog with common pool industry parts.

    Idempotent: skips existing SKUs, only inserts new ones.
    Returns count of inserted/skipped.
    """
    # Check how many already exist
    result = await db.execute(
        select(func.count(PartsCatalog.id)).where(PartsCatalog.vendor_provider == "scp")
    )
    existing_count = result.scalar() or 0

    inserted = 0
    skipped = 0

    for part_data in SEED_PARTS:
        result = await db.execute(
            select(PartsCatalog.id).where(
                PartsCatalog.vendor_provider == "scp",
                PartsCatalog.sku == part_data["sku"],
            )
        )
        if result.scalar_one_or_none():
            skipped += 1
            continue

        part = PartsCatalog(
            id=str(uuid.uuid4()),
            vendor_provider="scp",
            sku=part_data["sku"],
            name=part_data["name"],
            brand=part_data.get("brand"),
            category=part_data.get("category"),
            subcategory=part_data.get("subcategory"),
            description=part_data.get("description"),
            is_chemical=part_data.get("is_chemical", False),
            last_scraped_at=datetime.now(timezone.utc),
        )
        db.add(part)
        inserted += 1

    await db.flush()
    logger.info(f"Seed catalog: {inserted} inserted, {skipped} skipped (existing: {existing_count})")

    return {
        "total_seed_parts": len(SEED_PARTS),
        "inserted": inserted,
        "skipped": skipped,
        "existing_before": existing_count,
        "total_after": existing_count + inserted,
    }
