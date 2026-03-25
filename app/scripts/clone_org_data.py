"""Clone production org data into test org.

Creates independent copies of all entity data with new UUIDs.
Test org can be freely edited/deleted without affecting production.

Usage:
    cd /srv/quantumpools/app
    ../venv/bin/python -m scripts.clone_org_data
"""

import asyncio
import json
import uuid
from sqlalchemy import text
from src.core.database import get_engine


def jdump(val):
    """Serialize dicts/lists to JSON string for asyncpg."""
    if val is None:
        return None
    if isinstance(val, (dict, list)):
        return json.dumps(val)
    return val

PROD_ORG = "7ef7ab72-703f-45c1-847f-565101cb3e61"  # Sapphire Pool Service
TEST_ORG = "28bcb1c5-91a5-4af8-a2fe-0fe7fe4fc3b5"  # Test Pool Co


def new_id() -> str:
    return str(uuid.uuid4())


async def clone():
    engine = get_engine()
    async with engine.begin() as conn:
        # ── 0. Wipe existing test org data (reverse dependency order) ──
        print("Wiping existing test org data...")
        for tbl in [
            "dimension_estimates",
            "property_jurisdictions",
            "property_difficulties",
            "pool_measurements",
            "satellite_analyses",
            "chemical_readings",
            "water_features",
            "properties",
            "customers",
            "techs",
            "org_cost_settings",
        ]:
            r = await conn.execute(
                text(f"DELETE FROM {tbl} WHERE organization_id = :org"),
                {"org": TEST_ORG},
            )
            if r.rowcount:
                print(f"  Deleted {r.rowcount} from {tbl}")

        # ── 1. Customers ──
        print("\nCloning customers...")
        rows = await conn.execute(
            text("SELECT * FROM customers WHERE organization_id = :org AND is_active = true"),
            {"org": PROD_ORG},
        )
        customers = rows.mappings().all()
        cust_map = {}  # old_id -> new_id

        for c in customers:
            nid = new_id()
            cust_map[c["id"]] = nid
            await conn.execute(
                text("""
                    INSERT INTO customers (
                        id, organization_id, first_name, last_name, company_name,
                        customer_type, email, phone, billing_address, billing_city,
                        billing_state, billing_zip, service_frequency, preferred_day,
                        billing_frequency, monthly_rate, payment_method, payment_terms_days,
                        balance, difficulty_rating, notes, is_active, created_at, updated_at,
                        pss_id, autopay_enabled, status, display_name
                    ) VALUES (
                        :id, :org, :first_name, :last_name, :company_name,
                        :customer_type, :email, :phone, :billing_address, :billing_city,
                        :billing_state, :billing_zip, :service_frequency, :preferred_day,
                        :billing_frequency, :monthly_rate, :payment_method, :payment_terms_days,
                        0, :difficulty_rating, :notes, true, now(), now(),
                        :pss_id, :autopay_enabled, :status, :display_name
                    )
                """),
                {
                    "id": nid, "org": TEST_ORG,
                    "first_name": c["first_name"], "last_name": c["last_name"],
                    "company_name": c["company_name"], "customer_type": c["customer_type"],
                    "email": c["email"], "phone": c["phone"],
                    "billing_address": c["billing_address"], "billing_city": c["billing_city"],
                    "billing_state": c["billing_state"], "billing_zip": c["billing_zip"],
                    "service_frequency": c["service_frequency"], "preferred_day": c["preferred_day"],
                    "billing_frequency": c["billing_frequency"], "monthly_rate": c["monthly_rate"],
                    "payment_method": c["payment_method"], "payment_terms_days": c["payment_terms_days"],
                    "difficulty_rating": c["difficulty_rating"], "notes": c["notes"],
                    "pss_id": c["pss_id"], "autopay_enabled": c["autopay_enabled"],
                    "status": c["status"], "display_name": c["display_name"],
                },
            )
        print(f"  {len(customers)} customers cloned")

        # ── 2. Properties ──
        print("Cloning properties...")
        rows = await conn.execute(
            text("SELECT * FROM properties WHERE organization_id = :org AND is_active = true"),
            {"org": PROD_ORG},
        )
        properties = rows.mappings().all()
        prop_map = {}  # old_id -> new_id

        for p in properties:
            if p["customer_id"] not in cust_map:
                continue  # skip orphans or inactive customer refs
            nid = new_id()
            prop_map[p["id"]] = nid
            await conn.execute(
                text("""
                    INSERT INTO properties (
                        id, organization_id, customer_id, address, city, state, zip_code,
                        lat, lng, geocode_provider, pool_type, pool_gallons, pool_surface,
                        has_spa, has_water_feature, pump_type, filter_type, heater_type,
                        chlorinator_type, automation_system, gate_code, access_instructions,
                        dog_on_property, estimated_service_minutes, is_locked_to_day,
                        service_day_pattern, notes, is_active, created_at, updated_at,
                        pss_id, pool_sqft, pool_length_ft, pool_width_ft, pool_depth_shallow,
                        pool_depth_deep, pool_depth_avg, pool_shape, pool_volume_method,
                        name, monthly_rate, county, emd_fa_number
                    ) VALUES (
                        :id, :org, :cust, :address, :city, :state, :zip_code,
                        :lat, :lng, :geocode_provider, :pool_type, :pool_gallons, :pool_surface,
                        :has_spa, :has_water_feature, :pump_type, :filter_type, :heater_type,
                        :chlorinator_type, :automation_system, :gate_code, :access_instructions,
                        :dog_on_property, :estimated_service_minutes, :is_locked_to_day,
                        :service_day_pattern, :notes, true, now(), now(),
                        :pss_id, :pool_sqft, :pool_length_ft, :pool_width_ft, :pool_depth_shallow,
                        :pool_depth_deep, :pool_depth_avg, :pool_shape, :pool_volume_method,
                        :name, :monthly_rate, :county, :emd_fa_number
                    )
                """),
                {
                    "id": nid, "org": TEST_ORG, "cust": cust_map[p["customer_id"]],
                    "address": p["address"], "city": p["city"], "state": p["state"],
                    "zip_code": p["zip_code"], "lat": p["lat"], "lng": p["lng"],
                    "geocode_provider": p["geocode_provider"], "pool_type": p["pool_type"],
                    "pool_gallons": p["pool_gallons"], "pool_surface": p["pool_surface"],
                    "has_spa": p["has_spa"], "has_water_feature": p["has_water_feature"],
                    "pump_type": p["pump_type"], "filter_type": p["filter_type"],
                    "heater_type": p["heater_type"], "chlorinator_type": p["chlorinator_type"],
                    "automation_system": p["automation_system"], "gate_code": p["gate_code"],
                    "access_instructions": p["access_instructions"],
                    "dog_on_property": p["dog_on_property"],
                    "estimated_service_minutes": p["estimated_service_minutes"],
                    "is_locked_to_day": p["is_locked_to_day"],
                    "service_day_pattern": p["service_day_pattern"], "notes": p["notes"],
                    "pss_id": p["pss_id"], "pool_sqft": p["pool_sqft"],
                    "pool_length_ft": p["pool_length_ft"], "pool_width_ft": p["pool_width_ft"],
                    "pool_depth_shallow": p["pool_depth_shallow"],
                    "pool_depth_deep": p["pool_depth_deep"],
                    "pool_depth_avg": p["pool_depth_avg"], "pool_shape": p["pool_shape"],
                    "pool_volume_method": p["pool_volume_method"], "name": p["name"],
                    "monthly_rate": p["monthly_rate"], "county": p["county"],
                    "emd_fa_number": p["emd_fa_number"],
                },
            )
        print(f"  {len(prop_map)} properties cloned")

        # ── 3. Water Features (BOWs) ──
        print("Cloning water features...")
        old_prop_ids = list(prop_map.keys())
        if old_prop_ids:
            rows = await conn.execute(
                text(
                    "SELECT * FROM water_features WHERE property_id = ANY(:ids) AND is_active = true"
                ),
                {"ids": old_prop_ids},
            )
            wfs = rows.mappings().all()
        else:
            wfs = []
        wf_map = {}  # old_id -> new_id

        for w in wfs:
            if w["property_id"] not in prop_map:
                continue
            nid = new_id()
            wf_map[w["id"]] = nid
            await conn.execute(
                text("""
                    INSERT INTO water_features (
                        id, organization_id, property_id, name, water_type, pool_type,
                        pool_gallons, pool_sqft, pool_surface, pool_length_ft, pool_width_ft,
                        pool_depth_shallow, pool_depth_deep, pool_depth_avg, pool_shape,
                        pool_volume_method, pump_type, filter_type, heater_type,
                        chlorinator_type, automation_system, estimated_service_minutes,
                        monthly_rate, notes, is_active, created_at, updated_at,
                        sanitizer_type, dimension_source, dimension_source_date,
                        perimeter_ft, fill_method, drain_type, drain_method, drain_count,
                        drain_cover_compliant, drain_cover_install_date, drain_cover_expiry_date,
                        equalizer_cover_compliant, equalizer_cover_install_date,
                        equalizer_cover_expiry_date, plumbing_size_inches, pool_cover_type,
                        turnover_hours, skimmer_count, equipment_year, equipment_pad_location,
                        has_rounded_corners, step_entry_count, has_bench_shelf,
                        rate_allocation_method, rate_allocated_at, service_tier_id,
                        access_difficulty, chemical_demand, equipment_effectiveness,
                        pool_design, shade_exposure, tree_debris, emd_pr_number
                    ) VALUES (
                        :id, :org, :prop, :name, :water_type, :pool_type,
                        :pool_gallons, :pool_sqft, :pool_surface, :pool_length_ft, :pool_width_ft,
                        :pool_depth_shallow, :pool_depth_deep, :pool_depth_avg, :pool_shape,
                        :pool_volume_method, :pump_type, :filter_type, :heater_type,
                        :chlorinator_type, :automation_system, :estimated_service_minutes,
                        :monthly_rate, :notes, true, now(), now(),
                        :sanitizer_type, :dimension_source, :dimension_source_date,
                        :perimeter_ft, :fill_method, :drain_type, :drain_method, :drain_count,
                        :drain_cover_compliant, :drain_cover_install_date, :drain_cover_expiry_date,
                        :equalizer_cover_compliant, :equalizer_cover_install_date,
                        :equalizer_cover_expiry_date, :plumbing_size_inches, :pool_cover_type,
                        :turnover_hours, :skimmer_count, :equipment_year, :equipment_pad_location,
                        :has_rounded_corners, :step_entry_count, :has_bench_shelf,
                        :rate_allocation_method, :rate_allocated_at, :service_tier_id,
                        :access_difficulty, :chemical_demand, :equipment_effectiveness,
                        :pool_design, :shade_exposure, :tree_debris, :emd_pr_number
                    )
                """),
                {
                    "id": nid, "org": TEST_ORG, "prop": prop_map[w["property_id"]],
                    "name": w["name"], "water_type": w["water_type"], "pool_type": w["pool_type"],
                    "pool_gallons": w["pool_gallons"], "pool_sqft": w["pool_sqft"],
                    "pool_surface": w["pool_surface"], "pool_length_ft": w["pool_length_ft"],
                    "pool_width_ft": w["pool_width_ft"],
                    "pool_depth_shallow": w["pool_depth_shallow"],
                    "pool_depth_deep": w["pool_depth_deep"],
                    "pool_depth_avg": w["pool_depth_avg"], "pool_shape": w["pool_shape"],
                    "pool_volume_method": w["pool_volume_method"],
                    "pump_type": w["pump_type"], "filter_type": w["filter_type"],
                    "heater_type": w["heater_type"], "chlorinator_type": w["chlorinator_type"],
                    "automation_system": w["automation_system"],
                    "estimated_service_minutes": w["estimated_service_minutes"],
                    "monthly_rate": w["monthly_rate"], "notes": w["notes"],
                    "sanitizer_type": w["sanitizer_type"],
                    "dimension_source": w["dimension_source"],
                    "dimension_source_date": w["dimension_source_date"],
                    "perimeter_ft": w["perimeter_ft"], "fill_method": w["fill_method"],
                    "drain_type": w["drain_type"], "drain_method": w["drain_method"],
                    "drain_count": w["drain_count"],
                    "drain_cover_compliant": w["drain_cover_compliant"],
                    "drain_cover_install_date": w["drain_cover_install_date"],
                    "drain_cover_expiry_date": w["drain_cover_expiry_date"],
                    "equalizer_cover_compliant": w["equalizer_cover_compliant"],
                    "equalizer_cover_install_date": w["equalizer_cover_install_date"],
                    "equalizer_cover_expiry_date": w["equalizer_cover_expiry_date"],
                    "plumbing_size_inches": w["plumbing_size_inches"],
                    "pool_cover_type": w["pool_cover_type"],
                    "turnover_hours": w["turnover_hours"],
                    "skimmer_count": w["skimmer_count"],
                    "equipment_year": w["equipment_year"],
                    "equipment_pad_location": w["equipment_pad_location"],
                    "has_rounded_corners": w["has_rounded_corners"],
                    "step_entry_count": w["step_entry_count"],
                    "has_bench_shelf": w["has_bench_shelf"],
                    "rate_allocation_method": w["rate_allocation_method"],
                    "rate_allocated_at": w["rate_allocated_at"],
                    "service_tier_id": w["service_tier_id"],
                    "access_difficulty": w["access_difficulty"],
                    "chemical_demand": w["chemical_demand"],
                    "equipment_effectiveness": w["equipment_effectiveness"],
                    "pool_design": w["pool_design"],
                    "shade_exposure": w["shade_exposure"],
                    "tree_debris": w["tree_debris"],
                    "emd_pr_number": w["emd_pr_number"],
                },
            )
        print(f"  {len(wf_map)} water features cloned")

        # ── 4. Satellite Analyses ──
        print("Cloning satellite analyses...")
        if old_prop_ids:
            rows = await conn.execute(
                text("SELECT * FROM satellite_analyses WHERE property_id = ANY(:ids)"),
                {"ids": old_prop_ids},
            )
            sats = rows.mappings().all()
        else:
            sats = []
        sat_count = 0
        for s in sats:
            if s["property_id"] not in prop_map:
                continue
            new_wf_id = wf_map.get(s["water_feature_id"]) if s["water_feature_id"] else None
            await conn.execute(
                text("""
                    INSERT INTO satellite_analyses (
                        id, property_id, organization_id, pool_detected, estimated_pool_sqft,
                        pool_contour_points, pool_confidence, vegetation_pct, canopy_overhang_pct,
                        hardscape_pct, shadow_pct, image_url, image_zoom, image_width,
                        image_height, analysis_version, raw_results, error_message,
                        created_at, updated_at, pool_lat, pool_lng, water_feature_id
                    ) VALUES (
                        :id, :prop, :org, :pool_detected, :estimated_pool_sqft,
                        :pool_contour_points, :pool_confidence, :vegetation_pct, :canopy_overhang_pct,
                        :hardscape_pct, :shadow_pct, :image_url, :image_zoom, :image_width,
                        :image_height, :analysis_version, :raw_results, :error_message,
                        now(), now(), :pool_lat, :pool_lng, :wf
                    )
                """),
                {
                    "id": new_id(), "prop": prop_map[s["property_id"]], "org": TEST_ORG,
                    "pool_detected": s["pool_detected"],
                    "estimated_pool_sqft": s["estimated_pool_sqft"],
                    "pool_contour_points": jdump(s["pool_contour_points"]),
                    "pool_confidence": s["pool_confidence"],
                    "vegetation_pct": s["vegetation_pct"],
                    "canopy_overhang_pct": s["canopy_overhang_pct"],
                    "hardscape_pct": s["hardscape_pct"], "shadow_pct": s["shadow_pct"],
                    "image_url": s["image_url"], "image_zoom": s["image_zoom"],
                    "image_width": s["image_width"], "image_height": s["image_height"],
                    "analysis_version": s["analysis_version"],
                    "raw_results": jdump(s["raw_results"]), "error_message": s["error_message"],
                    "pool_lat": s["pool_lat"], "pool_lng": s["pool_lng"],
                    "wf": new_wf_id,
                },
            )
            sat_count += 1
        print(f"  {sat_count} satellite analyses cloned")

        # ── 5. Property Difficulties ──
        print("Cloning property difficulties...")
        if old_prop_ids:
            rows = await conn.execute(
                text("SELECT * FROM property_difficulties WHERE property_id = ANY(:ids)"),
                {"ids": old_prop_ids},
            )
            diffs = rows.mappings().all()
        else:
            diffs = []
        diff_count = 0
        for d in diffs:
            if d["property_id"] not in prop_map:
                continue
            new_wf_id = wf_map.get(d["water_feature_id"]) if d.get("water_feature_id") else None
            await conn.execute(
                text("""
                    INSERT INTO property_difficulties (
                        id, property_id, organization_id, shallow_sqft, deep_sqft, has_deep_end,
                        spa_sqft, diving_board_count, pump_flow_gpm, is_indoor,
                        equipment_age_years, shade_exposure, tree_debris_level, enclosure_type,
                        chem_feeder_type, access_difficulty_score, customer_demands_score,
                        chemical_demand_score, callback_frequency_score, override_composite,
                        notes, created_at, updated_at, water_feature_id,
                        res_tree_debris, res_dog, res_customer_demands,
                        res_system_effectiveness, equipment_effectiveness, pool_design_score
                    ) VALUES (
                        :id, :prop, :org, :shallow_sqft, :deep_sqft, :has_deep_end,
                        :spa_sqft, :diving_board_count, :pump_flow_gpm, :is_indoor,
                        :equipment_age_years, :shade_exposure, :tree_debris_level, :enclosure_type,
                        :chem_feeder_type, :access_difficulty_score, :customer_demands_score,
                        :chemical_demand_score, :callback_frequency_score, :override_composite,
                        :notes, now(), now(), :wf,
                        :res_tree_debris, :res_dog, :res_customer_demands,
                        :res_system_effectiveness, :equipment_effectiveness, :pool_design_score
                    )
                """),
                {
                    "id": new_id(), "prop": prop_map[d["property_id"]], "org": TEST_ORG,
                    "shallow_sqft": d["shallow_sqft"], "deep_sqft": d["deep_sqft"],
                    "has_deep_end": d["has_deep_end"], "spa_sqft": d["spa_sqft"],
                    "diving_board_count": d["diving_board_count"],
                    "pump_flow_gpm": d["pump_flow_gpm"], "is_indoor": d["is_indoor"],
                    "equipment_age_years": d["equipment_age_years"],
                    "shade_exposure": d["shade_exposure"],
                    "tree_debris_level": d["tree_debris_level"],
                    "enclosure_type": d["enclosure_type"],
                    "chem_feeder_type": d["chem_feeder_type"],
                    "access_difficulty_score": d["access_difficulty_score"],
                    "customer_demands_score": d["customer_demands_score"],
                    "chemical_demand_score": d["chemical_demand_score"],
                    "callback_frequency_score": d["callback_frequency_score"],
                    "override_composite": d["override_composite"], "notes": d["notes"],
                    "wf": new_wf_id,
                    "res_tree_debris": d["res_tree_debris"], "res_dog": d["res_dog"],
                    "res_customer_demands": d["res_customer_demands"],
                    "res_system_effectiveness": d["res_system_effectiveness"],
                    "equipment_effectiveness": d["equipment_effectiveness"],
                    "pool_design_score": d["pool_design_score"],
                },
            )
            diff_count += 1
        print(f"  {diff_count} property difficulties cloned")

        # ── 6. Pool Measurements ──
        print("Cloning pool measurements...")
        if old_prop_ids:
            rows = await conn.execute(
                text("SELECT * FROM pool_measurements WHERE property_id = ANY(:ids)"),
                {"ids": old_prop_ids},
            )
            measurements = rows.mappings().all()
        else:
            measurements = []
        meas_count = 0
        for m in measurements:
            if m["property_id"] not in prop_map:
                continue
            new_wf_id = wf_map.get(m["water_feature_id"]) if m.get("water_feature_id") else None
            await conn.execute(
                text("""
                    INSERT INTO pool_measurements (
                        id, property_id, organization_id, measured_by, length_ft, width_ft,
                        depth_shallow_ft, depth_deep_ft, depth_avg_ft, calculated_sqft,
                        calculated_gallons, pool_shape, scale_reference, confidence,
                        photo_paths, raw_analysis, error_message, status,
                        applied_to_property, created_at, updated_at, water_feature_id
                    ) VALUES (
                        :id, :prop, :org, :measured_by, :length_ft, :width_ft,
                        :depth_shallow_ft, :depth_deep_ft, :depth_avg_ft, :calculated_sqft,
                        :calculated_gallons, :pool_shape, :scale_reference, :confidence,
                        :photo_paths, :raw_analysis, :error_message, :status,
                        :applied_to_property, now(), now(), :wf
                    )
                """),
                {
                    "id": new_id(), "prop": prop_map[m["property_id"]], "org": TEST_ORG,
                    "measured_by": m["measured_by"], "length_ft": m["length_ft"],
                    "width_ft": m["width_ft"], "depth_shallow_ft": m["depth_shallow_ft"],
                    "depth_deep_ft": m["depth_deep_ft"], "depth_avg_ft": m["depth_avg_ft"],
                    "calculated_sqft": m["calculated_sqft"],
                    "calculated_gallons": m["calculated_gallons"],
                    "pool_shape": m["pool_shape"], "scale_reference": m["scale_reference"],
                    "confidence": m["confidence"], "photo_paths": jdump(m["photo_paths"]),
                    "raw_analysis": jdump(m["raw_analysis"]), "error_message": m["error_message"],
                    "status": m["status"], "applied_to_property": m["applied_to_property"],
                    "wf": new_wf_id,
                },
            )
            meas_count += 1
        print(f"  {meas_count} pool measurements cloned")

        # ── 7. Techs (clone without user_id — test techs are standalone) ──
        print("Cloning techs...")
        rows = await conn.execute(
            text("SELECT * FROM techs WHERE organization_id = :org AND is_active = true"),
            {"org": PROD_ORG},
        )
        techs = rows.mappings().all()
        tech_count = 0
        for t in techs:
            await conn.execute(
                text("""
                    INSERT INTO techs (
                        id, organization_id, first_name, last_name, email, phone, color,
                        start_lat, start_lng, start_address, end_lat, end_lng, end_address,
                        work_start_time, work_end_time, working_days, max_stops_per_day,
                        efficiency_factor, is_active, created_at, updated_at,
                        hourly_rate, overtime_rate, skills, certifications, service_types,
                        territory_zone, vehicle_type, vehicle_plate, job_title, hire_date, notes
                    ) VALUES (
                        :id, :org, :first_name, :last_name, :email, :phone, :color,
                        :start_lat, :start_lng, :start_address, :end_lat, :end_lng, :end_address,
                        :work_start_time, :work_end_time, :working_days, :max_stops_per_day,
                        :efficiency_factor, true, now(), now(),
                        :hourly_rate, :overtime_rate, :skills, :certifications, :service_types,
                        :territory_zone, :vehicle_type, :vehicle_plate, :job_title, :hire_date, :notes
                    )
                """),
                {
                    "id": new_id(), "org": TEST_ORG,
                    "first_name": t["first_name"], "last_name": t["last_name"],
                    "email": t["email"], "phone": t["phone"], "color": t["color"],
                    "start_lat": t["start_lat"], "start_lng": t["start_lng"],
                    "start_address": t["start_address"],
                    "end_lat": t["end_lat"], "end_lng": t["end_lng"],
                    "end_address": t["end_address"],
                    "work_start_time": t["work_start_time"],
                    "work_end_time": t["work_end_time"],
                    "working_days": jdump(t["working_days"]),
                    "max_stops_per_day": t["max_stops_per_day"],
                    "efficiency_factor": t["efficiency_factor"],
                    "hourly_rate": t["hourly_rate"], "overtime_rate": t["overtime_rate"],
                    "skills": jdump(t["skills"]), "certifications": jdump(t["certifications"]),
                    "service_types": jdump(t["service_types"]),
                    "territory_zone": t["territory_zone"],
                    "vehicle_type": t["vehicle_type"], "vehicle_plate": t["vehicle_plate"],
                    "job_title": t["job_title"], "hire_date": t["hire_date"],
                    "notes": t["notes"],
                },
            )
            tech_count += 1
        print(f"  {tech_count} techs cloned")

        # ── 8. Org Cost Settings ──
        print("Cloning org cost settings...")
        rows = await conn.execute(
            text("SELECT * FROM org_cost_settings WHERE organization_id = :org"),
            {"org": PROD_ORG},
        )
        cost_settings = rows.mappings().all()
        for cs in cost_settings:
            await conn.execute(
                text("""
                    INSERT INTO org_cost_settings (
                        id, organization_id, burdened_labor_rate, vehicle_cost_per_mile,
                        chemical_cost_per_gallon, monthly_overhead, target_margin_pct,
                        created_at, updated_at, semi_annual_discount_type,
                        semi_annual_discount_value, annual_discount_type, annual_discount_value,
                        avg_drive_minutes, avg_drive_miles, visits_per_month,
                        residential_overhead_per_account, commercial_overhead_per_account
                    ) VALUES (
                        :id, :org, :burdened_labor_rate, :vehicle_cost_per_mile,
                        :chemical_cost_per_gallon, :monthly_overhead, :target_margin_pct,
                        now(), now(), :semi_annual_discount_type,
                        :semi_annual_discount_value, :annual_discount_type, :annual_discount_value,
                        :avg_drive_minutes, :avg_drive_miles, :visits_per_month,
                        :residential_overhead_per_account, :commercial_overhead_per_account
                    )
                """),
                {
                    "id": new_id(), "org": TEST_ORG,
                    "burdened_labor_rate": cs["burdened_labor_rate"],
                    "vehicle_cost_per_mile": cs["vehicle_cost_per_mile"],
                    "chemical_cost_per_gallon": cs["chemical_cost_per_gallon"],
                    "monthly_overhead": cs["monthly_overhead"],
                    "target_margin_pct": cs["target_margin_pct"],
                    "semi_annual_discount_type": cs["semi_annual_discount_type"],
                    "semi_annual_discount_value": cs["semi_annual_discount_value"],
                    "annual_discount_type": cs["annual_discount_type"],
                    "annual_discount_value": cs["annual_discount_value"],
                    "avg_drive_minutes": cs["avg_drive_minutes"],
                    "avg_drive_miles": cs["avg_drive_miles"],
                    "visits_per_month": cs["visits_per_month"],
                    "residential_overhead_per_account": cs["residential_overhead_per_account"],
                    "commercial_overhead_per_account": cs["commercial_overhead_per_account"],
                },
            )
        print(f"  {len(cost_settings)} cost settings cloned")

        # ── 9. Property Jurisdictions ──
        print("Cloning property jurisdictions...")
        if old_prop_ids:
            rows = await conn.execute(
                text("SELECT * FROM property_jurisdictions WHERE property_id = ANY(:ids)"),
                {"ids": old_prop_ids},
            )
            jurisdictions = rows.mappings().all()
        else:
            jurisdictions = []
        jur_count = 0
        for j in jurisdictions:
            if j["property_id"] not in prop_map:
                continue
            new_wf_id = wf_map.get(j["water_feature_id"]) if j.get("water_feature_id") else None
            await conn.execute(
                text("""
                    INSERT INTO property_jurisdictions (
                        id, property_id, jurisdiction_id, organization_id, water_feature_id
                    ) VALUES (:id, :prop, :jur, :org, :wf)
                """),
                {
                    "id": new_id(), "prop": prop_map[j["property_id"]],
                    "jur": j["jurisdiction_id"], "org": TEST_ORG,
                    "wf": new_wf_id,
                },
            )
            jur_count += 1
        print(f"  {jur_count} property jurisdictions cloned")

        # ── 10. Dimension Estimates ──
        print("Cloning dimension estimates...")
        old_wf_ids = list(wf_map.keys())
        if old_wf_ids:
            rows = await conn.execute(
                text("SELECT * FROM dimension_estimates WHERE water_feature_id = ANY(:ids)"),
                {"ids": old_wf_ids},
            )
            dim_ests = rows.mappings().all()
        else:
            dim_ests = []
        dim_count = 0
        for de in dim_ests:
            if de["water_feature_id"] not in wf_map:
                continue
            await conn.execute(
                text("""
                    INSERT INTO dimension_estimates (
                        id, water_feature_id, organization_id, source, estimated_sqft,
                        perimeter_ft, raw_data, notes, created_by, created_at
                    ) VALUES (
                        :id, :wf, :org, :source, :estimated_sqft,
                        :perimeter_ft, :raw_data, :notes, :created_by, now()
                    )
                """),
                {
                    "id": new_id(), "wf": wf_map[de["water_feature_id"]], "org": TEST_ORG,
                    "source": de["source"], "estimated_sqft": de["estimated_sqft"],
                    "perimeter_ft": de["perimeter_ft"], "raw_data": jdump(de["raw_data"]),
                    "notes": de["notes"], "created_by": de["created_by"],
                },
            )
            dim_count += 1
        print(f"  {dim_count} dimension estimates cloned")

    print("\n✓ Clone complete. Test Pool Co now has a full copy of production data.")


if __name__ == "__main__":
    asyncio.run(clone())
