--
-- PostgreSQL database dump
--

\restrict WDclYOfgXgob3ktolVSQoLgVg4fLHcUW72YRIwWSGgebdmoNvodTyEAlbIqbH6V

-- Dumped from database version 15.14 (Debian 15.14-0+deb12u1)
-- Dumped by pg_dump version 15.14 (Debian 15.14-0+deb12u1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: alembic_version; Type: TABLE; Schema: public; Owner: routeoptimizer
--

CREATE TABLE public.alembic_version (
    version_num character varying(32) NOT NULL
);


ALTER TABLE public.alembic_version OWNER TO routeoptimizer;

--
-- Name: customers; Type: TABLE; Schema: public; Owner: routeoptimizer
--

CREATE TABLE public.customers (
    id uuid NOT NULL,
    name character varying(200),
    address character varying(500) NOT NULL,
    latitude double precision,
    longitude double precision,
    service_type character varying(20) NOT NULL,
    difficulty integer NOT NULL,
    service_day character varying(20) NOT NULL,
    locked boolean NOT NULL,
    time_window_start time without time zone,
    time_window_end time without time zone,
    notes character varying(1000),
    is_active boolean NOT NULL,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL,
    service_days_per_week integer NOT NULL,
    service_schedule character varying(50),
    assigned_driver_id uuid,
    visit_duration integer DEFAULT 15 NOT NULL,
    first_name character varying(100),
    last_name character varying(100),
    display_name character varying(200) NOT NULL,
    email character varying(255),
    phone character varying(20),
    alt_email character varying(255),
    alt_phone character varying(20),
    invoice_email character varying(255),
    management_company character varying(200),
    status character varying(20) DEFAULT 'active'::character varying NOT NULL,
    service_rate numeric(10,2),
    billing_frequency character varying(20),
    rate_notes character varying(500),
    payment_method_type character varying(20),
    stripe_customer_id character varying(100),
    stripe_payment_method_id character varying(100),
    payment_last_four character varying(4),
    payment_brand character varying(50)
);


ALTER TABLE public.customers OWNER TO routeoptimizer;

--
-- Name: COLUMN customers.name; Type: COMMENT; Schema: public; Owner: routeoptimizer
--

COMMENT ON COLUMN public.customers.name IS 'Business name (for commercial) or full name (legacy)';


--
-- Name: COLUMN customers.service_type; Type: COMMENT; Schema: public; Owner: routeoptimizer
--

COMMENT ON COLUMN public.customers.service_type IS 'residential or commercial';


--
-- Name: COLUMN customers.difficulty; Type: COMMENT; Schema: public; Owner: routeoptimizer
--

COMMENT ON COLUMN public.customers.difficulty IS '1-5 difficulty scale affecting service duration';


--
-- Name: COLUMN customers.service_day; Type: COMMENT; Schema: public; Owner: routeoptimizer
--

COMMENT ON COLUMN public.customers.service_day IS 'Primary service day: monday, tuesday, wednesday, thursday, friday, saturday, sunday';


--
-- Name: COLUMN customers.locked; Type: COMMENT; Schema: public; Owner: routeoptimizer
--

COMMENT ON COLUMN public.customers.locked IS 'If true, cannot be moved to a different service day during optimization';


--
-- Name: COLUMN customers.time_window_start; Type: COMMENT; Schema: public; Owner: routeoptimizer
--

COMMENT ON COLUMN public.customers.time_window_start IS 'Earliest time customer can be serviced';


--
-- Name: COLUMN customers.time_window_end; Type: COMMENT; Schema: public; Owner: routeoptimizer
--

COMMENT ON COLUMN public.customers.time_window_end IS 'Latest time customer can be serviced';


--
-- Name: COLUMN customers.service_days_per_week; Type: COMMENT; Schema: public; Owner: routeoptimizer
--

COMMENT ON COLUMN public.customers.service_days_per_week IS 'Number of service days per week (1, 2, or 3)';


--
-- Name: COLUMN customers.service_schedule; Type: COMMENT; Schema: public; Owner: routeoptimizer
--

COMMENT ON COLUMN public.customers.service_schedule IS 'Current schedule pattern (e.g., ''Mo/Th'', ''Mo/We/Fr''). NULL for single-day schedules.';


--
-- Name: COLUMN customers.assigned_driver_id; Type: COMMENT; Schema: public; Owner: routeoptimizer
--

COMMENT ON COLUMN public.customers.assigned_driver_id IS 'Driver assigned to service this customer';


--
-- Name: COLUMN customers.visit_duration; Type: COMMENT; Schema: public; Owner: routeoptimizer
--

COMMENT ON COLUMN public.customers.visit_duration IS 'Visit duration in minutes';


--
-- Name: COLUMN customers.first_name; Type: COMMENT; Schema: public; Owner: routeoptimizer
--

COMMENT ON COLUMN public.customers.first_name IS 'First name (for residential)';


--
-- Name: COLUMN customers.last_name; Type: COMMENT; Schema: public; Owner: routeoptimizer
--

COMMENT ON COLUMN public.customers.last_name IS 'Last name (for residential)';


--
-- Name: COLUMN customers.display_name; Type: COMMENT; Schema: public; Owner: routeoptimizer
--

COMMENT ON COLUMN public.customers.display_name IS 'Display name (auto-generated if not provided)';


--
-- Name: COLUMN customers.email; Type: COMMENT; Schema: public; Owner: routeoptimizer
--

COMMENT ON COLUMN public.customers.email IS 'Primary email address';


--
-- Name: COLUMN customers.phone; Type: COMMENT; Schema: public; Owner: routeoptimizer
--

COMMENT ON COLUMN public.customers.phone IS 'Primary phone number';


--
-- Name: COLUMN customers.alt_email; Type: COMMENT; Schema: public; Owner: routeoptimizer
--

COMMENT ON COLUMN public.customers.alt_email IS 'Alternate email address';


--
-- Name: COLUMN customers.alt_phone; Type: COMMENT; Schema: public; Owner: routeoptimizer
--

COMMENT ON COLUMN public.customers.alt_phone IS 'Alternate phone number';


--
-- Name: COLUMN customers.invoice_email; Type: COMMENT; Schema: public; Owner: routeoptimizer
--

COMMENT ON COLUMN public.customers.invoice_email IS 'Invoice email (for commercial)';


--
-- Name: COLUMN customers.management_company; Type: COMMENT; Schema: public; Owner: routeoptimizer
--

COMMENT ON COLUMN public.customers.management_company IS 'Management company name (for commercial)';


--
-- Name: COLUMN customers.status; Type: COMMENT; Schema: public; Owner: routeoptimizer
--

COMMENT ON COLUMN public.customers.status IS 'Customer status: pending, active, inactive';


--
-- Name: COLUMN customers.service_rate; Type: COMMENT; Schema: public; Owner: routeoptimizer
--

COMMENT ON COLUMN public.customers.service_rate IS 'Service rate amount (e.g., 125.00 for $125)';


--
-- Name: COLUMN customers.billing_frequency; Type: COMMENT; Schema: public; Owner: routeoptimizer
--

COMMENT ON COLUMN public.customers.billing_frequency IS 'Billing frequency: weekly, monthly, per-visit';


--
-- Name: COLUMN customers.rate_notes; Type: COMMENT; Schema: public; Owner: routeoptimizer
--

COMMENT ON COLUMN public.customers.rate_notes IS 'Special pricing notes or agreements';


--
-- Name: COLUMN customers.payment_method_type; Type: COMMENT; Schema: public; Owner: routeoptimizer
--

COMMENT ON COLUMN public.customers.payment_method_type IS 'Payment method: credit_card, ach, check, cash';


--
-- Name: COLUMN customers.stripe_customer_id; Type: COMMENT; Schema: public; Owner: routeoptimizer
--

COMMENT ON COLUMN public.customers.stripe_customer_id IS 'Stripe customer ID for payment processing';


--
-- Name: COLUMN customers.stripe_payment_method_id; Type: COMMENT; Schema: public; Owner: routeoptimizer
--

COMMENT ON COLUMN public.customers.stripe_payment_method_id IS 'Stripe payment method ID';


--
-- Name: COLUMN customers.payment_last_four; Type: COMMENT; Schema: public; Owner: routeoptimizer
--

COMMENT ON COLUMN public.customers.payment_last_four IS 'Last 4 digits of card/account for display only';


--
-- Name: COLUMN customers.payment_brand; Type: COMMENT; Schema: public; Owner: routeoptimizer
--

COMMENT ON COLUMN public.customers.payment_brand IS 'Card brand (Visa, Mastercard, etc.) or bank name';


--
-- Name: drivers; Type: TABLE; Schema: public; Owner: routeoptimizer
--

CREATE TABLE public.drivers (
    id uuid NOT NULL,
    name character varying(200) NOT NULL,
    email character varying(255),
    phone character varying(20),
    start_location_address character varying(500) NOT NULL,
    start_latitude double precision,
    start_longitude double precision,
    end_location_address character varying(500) NOT NULL,
    end_latitude double precision,
    end_longitude double precision,
    working_hours_start time without time zone NOT NULL,
    working_hours_end time without time zone NOT NULL,
    max_customers_per_day integer NOT NULL,
    is_active boolean NOT NULL,
    notes character varying(1000),
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL,
    color character varying(7) DEFAULT '#3498db'::character varying NOT NULL
);


ALTER TABLE public.drivers OWNER TO routeoptimizer;

--
-- Name: COLUMN drivers.working_hours_start; Type: COMMENT; Schema: public; Owner: routeoptimizer
--

COMMENT ON COLUMN public.drivers.working_hours_start IS 'Start of workday';


--
-- Name: COLUMN drivers.working_hours_end; Type: COMMENT; Schema: public; Owner: routeoptimizer
--

COMMENT ON COLUMN public.drivers.working_hours_end IS 'End of workday';


--
-- Name: COLUMN drivers.max_customers_per_day; Type: COMMENT; Schema: public; Owner: routeoptimizer
--

COMMENT ON COLUMN public.drivers.max_customers_per_day IS 'Maximum number of customers this driver can service in one day';


--
-- Name: COLUMN drivers.is_active; Type: COMMENT; Schema: public; Owner: routeoptimizer
--

COMMENT ON COLUMN public.drivers.is_active IS 'Whether this driver is currently active/available';


--
-- Name: COLUMN drivers.color; Type: COMMENT; Schema: public; Owner: routeoptimizer
--

COMMENT ON COLUMN public.drivers.color IS 'Hex color code for route visualization';


--
-- Name: route_stops; Type: TABLE; Schema: public; Owner: routeoptimizer
--

CREATE TABLE public.route_stops (
    id uuid NOT NULL,
    route_id uuid NOT NULL,
    customer_id uuid NOT NULL,
    sequence integer NOT NULL,
    estimated_arrival_time time without time zone,
    estimated_service_duration integer,
    estimated_drive_time_from_previous integer,
    estimated_distance_from_previous double precision,
    created_at timestamp without time zone NOT NULL
);


ALTER TABLE public.route_stops OWNER TO routeoptimizer;

--
-- Name: COLUMN route_stops.sequence; Type: COMMENT; Schema: public; Owner: routeoptimizer
--

COMMENT ON COLUMN public.route_stops.sequence IS 'Order of this stop in the route (1-based)';


--
-- Name: COLUMN route_stops.estimated_arrival_time; Type: COMMENT; Schema: public; Owner: routeoptimizer
--

COMMENT ON COLUMN public.route_stops.estimated_arrival_time IS 'Estimated time of arrival at this customer';


--
-- Name: COLUMN route_stops.estimated_service_duration; Type: COMMENT; Schema: public; Owner: routeoptimizer
--

COMMENT ON COLUMN public.route_stops.estimated_service_duration IS 'Estimated service time in minutes';


--
-- Name: COLUMN route_stops.estimated_drive_time_from_previous; Type: COMMENT; Schema: public; Owner: routeoptimizer
--

COMMENT ON COLUMN public.route_stops.estimated_drive_time_from_previous IS 'Estimated driving time from previous stop in minutes';


--
-- Name: COLUMN route_stops.estimated_distance_from_previous; Type: COMMENT; Schema: public; Owner: routeoptimizer
--

COMMENT ON COLUMN public.route_stops.estimated_distance_from_previous IS 'Distance from previous stop in miles';


--
-- Name: routes; Type: TABLE; Schema: public; Owner: routeoptimizer
--

CREATE TABLE public.routes (
    id uuid NOT NULL,
    driver_id uuid NOT NULL,
    service_day character varying(20) NOT NULL,
    total_duration_minutes integer,
    total_distance_miles double precision,
    total_customers integer,
    optimization_algorithm character varying(100),
    optimization_score double precision,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


ALTER TABLE public.routes OWNER TO routeoptimizer;

--
-- Name: COLUMN routes.service_day; Type: COMMENT; Schema: public; Owner: routeoptimizer
--

COMMENT ON COLUMN public.routes.service_day IS 'monday, tuesday, wednesday, thursday, friday, saturday, sunday';


--
-- Name: COLUMN routes.total_duration_minutes; Type: COMMENT; Schema: public; Owner: routeoptimizer
--

COMMENT ON COLUMN public.routes.total_duration_minutes IS 'Total route duration including driving and service time';


--
-- Name: COLUMN routes.total_distance_miles; Type: COMMENT; Schema: public; Owner: routeoptimizer
--

COMMENT ON COLUMN public.routes.total_distance_miles IS 'Total driving distance in miles';


--
-- Name: COLUMN routes.total_customers; Type: COMMENT; Schema: public; Owner: routeoptimizer
--

COMMENT ON COLUMN public.routes.total_customers IS 'Total number of customers on this route';


--
-- Name: COLUMN routes.optimization_algorithm; Type: COMMENT; Schema: public; Owner: routeoptimizer
--

COMMENT ON COLUMN public.routes.optimization_algorithm IS 'Algorithm used to generate this route';


--
-- Name: COLUMN routes.optimization_score; Type: COMMENT; Schema: public; Owner: routeoptimizer
--

COMMENT ON COLUMN public.routes.optimization_score IS 'Quality score of the optimization (if available)';


--
-- Data for Name: alembic_version; Type: TABLE DATA; Schema: public; Owner: routeoptimizer
--

COPY public.alembic_version (version_num) FROM stdin;
87709476bf43
\.


--
-- Data for Name: customers; Type: TABLE DATA; Schema: public; Owner: routeoptimizer
--

COPY public.customers (id, name, address, latitude, longitude, service_type, difficulty, service_day, locked, time_window_start, time_window_end, notes, is_active, created_at, updated_at, service_days_per_week, service_schedule, assigned_driver_id, visit_duration, first_name, last_name, display_name, email, phone, alt_email, alt_phone, invoice_email, management_company, status, service_rate, billing_frequency, rate_notes, payment_method_type, stripe_customer_id, stripe_payment_method_id, payment_last_four, payment_brand) FROM stdin;
316f86f7-fe09-4a77-82ea-8d6403815496	The Trees at Madison	5101 Hackberry Ln, Sacramento, CA, 95841	38.6582499	-121.3321344	commercial	1	monday	f	\N	\N	\N	t	2025-10-24 02:45:32.520739	2025-10-25 14:49:49.486641	2	Mo/Th	\N	25	\N	\N	The Trees at Madison	\N	\N	\N	\N	\N	BLVD	active	\N	\N	\N	\N	\N	\N	\N	\N
c7eeab93-8696-426f-8a26-e32f51c2098d	Madison Apartment Homes #1	4901 Little Oak Lane, Sacramento, CA, 95841	38.65464	-121.347231	commercial	1	monday	f	\N	\N	\N	t	2025-10-24 02:45:32.52064	2025-10-25 17:25:15.738522	3	Mo/We/Fr	\N	25	\N	\N	Madison Apartment Homes #1	\N	\N	\N	\N	\N	Conam	active	\N	\N	\N	\N	\N	\N	\N	\N
51a2a7ea-69d5-428d-adf0-ff69107e8137	Coventry Park	751 Central Park Drive, Roseville, CA, 95678	38.7890915	-121.2751283	commercial	1	monday	f	\N	\N	\N	t	2025-10-24 02:45:32.520606	2025-10-25 17:26:25.448592	3	Mo/We/Fr	\N	25	\N	\N	Coventry Park	\N	\N	\N	\N	\N	Conam	active	\N	\N	\N	\N	\N	\N	\N	\N
efce8880-3c9d-4746-bc8c-aee76695d238	Ten Forty	1040 Fulton Ave, Sacramento, CA, 95825	38.5836414	-121.4013718	commercial	1	monday	f	\N	\N	\N	t	2025-10-24 02:45:32.520731	2025-10-26 18:02:33.570956	2	Mo/Th	28e669ac-f113-42e3-affa-59d98dae5972	25	\N	\N	Ten Forty	\N	\N	\N	\N	\N	\N	active	\N	\N	\N	\N	\N	\N	\N	\N
8bae33fe-08be-471a-9178-98ef08ce531e	Learn Jeff	760 Hawkcrest Circle, Sacramento, CA 95835	38.65	-121.51	residential	1	tuesday	f	\N	\N	\N	t	2025-10-24 02:25:27.897741	2025-10-25 16:09:54.721224	1	\N	\N	15	Jeff	Learn	Learn, Jeff	\N	\N	\N	\N	\N	\N	active	\N	\N	\N	\N	\N	\N	\N	\N
c7d28bbb-5244-416f-b026-614baf69ef66	Maghan Tim	2133 Gold Haven Court, Gold River, CA 95670	38.6296	-121.2466	residential	1	tuesday	f	\N	\N	\N	t	2025-10-24 02:25:27.897747	2025-10-25 16:09:54.721226	1	\N	\N	15	Tim	Maghan	Maghan, Tim	\N	\N	\N	\N	\N	\N	active	\N	\N	\N	\N	\N	\N	\N	\N
d6abe7fd-ec38-42f3-9ac9-ed4432579bc3	Lew Keith	4428 Walali Way, Fair Oaks, CA 95628	38.6446	-121.2722	residential	1	thursday	f	\N	\N	\N	t	2025-10-24 02:25:27.897743	2025-10-25 16:09:54.721227	1	\N	\N	15	Keith	Lew	Lew, Keith	\N	\N	\N	\N	\N	\N	active	\N	\N	\N	\N	\N	\N	\N	\N
f295e2cc-7345-4023-beda-4417de4e490b	Koon John & McKenna	8763 Kevmich Way, Orangevale, CA 95662	38.67	-121.22	residential	1	thursday	f	\N	\N	\N	t	2025-10-24 02:25:27.897736	2025-10-25 16:09:54.721228	1	\N	\N	15	John & McKenna	Koon	Koon, John & McKenna	\N	\N	\N	\N	\N	\N	active	\N	\N	\N	\N	\N	\N	\N	\N
f9cb219f-4acd-4067-b35b-ea47afe129fb	Garcia Patty & Mattesich	840 Casmalia Way, Sacramento, CA 95864	38.59	-121.37	residential	1	wednesday	f	\N	\N	\N	t	2025-10-24 02:25:27.897719	2025-10-25 16:09:54.721228	1	\N	\N	15	Patty & Mattesich	Garcia	Garcia, Patty & Mattesich	\N	\N	\N	\N	\N	\N	active	\N	\N	\N	\N	\N	\N	\N	\N
2e0215e0-2047-482e-a07a-80865f7f0819	Twelve55 Living	1255 University Ave, Sacramento, CA, 95825	38.5617099	-121.4150686	commercial	1	monday	f	\N	\N	\N	t	2025-10-24 02:45:32.520742	2025-10-26 18:02:34.542246	2	Mo/Th	28e669ac-f113-42e3-affa-59d98dae5972	25	\N	\N	Twelve55 Living	\N	\N	\N	\N	\N	\N	active	\N	\N	\N	\N	\N	\N	\N	\N
cdffa864-f510-4283-95ab-3f188e66b4f2	Stonebrook	7002 East Parkway, Sacramento, CA, 95823	38.4979453	-121.4509033	commercial	1	monday	f	\N	\N	\N	t	2025-10-24 02:45:32.520724	2025-10-26 18:02:38.421742	3	Mo/We/Fr	28e669ac-f113-42e3-affa-59d98dae5972	25	\N	\N	Stonebrook	\N	\N	\N	\N	\N	\N	active	\N	\N	\N	\N	\N	\N	\N	\N
20260625-ff56-4f93-8603-f69c239bc27f	Madison Apartment Homes #2	4901 Little Oak Lane, Sacramento, CA 95841	38.63	-121.41	commercial	1	monday	f	\N	\N	\N	t	2025-10-24 02:45:32.520645	2025-10-24 02:45:32.520646	3	Mo/We/Fr	\N	25	\N	\N	Madison Apartment Homes #2	\N	\N	\N	\N	\N	\N	active	\N	\N	\N	\N	\N	\N	\N	\N
0d3052f0-238e-4d14-9304-d59f8a7350c3	Madison Apartment Homes #3	4901 Little Oak Lane, Sacramento, CA 95841	38.63	-121.41	commercial	1	monday	f	\N	\N	\N	t	2025-10-24 02:45:32.52065	2025-10-24 02:45:32.520651	3	Mo/We/Fr	\N	25	\N	\N	Madison Apartment Homes #3	\N	\N	\N	\N	\N	\N	active	\N	\N	\N	\N	\N	\N	\N	\N
36da7f96-fee2-40d7-a8df-f305b34fbbde	Slate Creek - Office Pool	8800 Sierra College Blvd, Roseville, CA 95661	38.75	-121.23	commercial	1	monday	f	\N	\N	\N	t	2025-10-24 02:45:32.520713	2025-10-24 02:45:32.520714	3	Mo/We/Fr	\N	25	\N	\N	Slate Creek - Office Pool	\N	\N	\N	\N	\N	\N	active	\N	\N	\N	\N	\N	\N	\N	\N
88c76416-e87f-4eeb-bc08-c08e17656848	Slate Creek - Lounge Pool	8800 Sierra College Blvd, Roseville, CA 95661	38.75	-121.23	commercial	1	monday	f	\N	\N	\N	t	2025-10-24 02:45:32.520717	2025-10-24 02:45:32.520717	3	Mo/We/Fr	\N	25	\N	\N	Slate Creek - Lounge Pool	\N	\N	\N	\N	\N	\N	active	\N	\N	\N	\N	\N	\N	\N	\N
9b427614-f2a8-4b59-8e30-2ba3c249f87e	Slate Creek - Fitness	8800 Sierra College Blvd, Roseville, CA 95661	38.75	-121.23	commercial	1	monday	f	\N	\N	\N	t	2025-10-24 02:45:32.52072	2025-10-24 02:45:32.520721	3	Mo/We/Fr	\N	25	\N	\N	Slate Creek - Fitness	\N	\N	\N	\N	\N	\N	active	\N	\N	\N	\N	\N	\N	\N	\N
4949dd43-4984-4017-9aa9-550953d8359b	The Bridges at Woodcreek Oaks	7950 Foothills Blvd, Roseville, CA 95747	38.7811	-121.3156	commercial	1	monday	f	\N	\N	\N	t	2025-10-24 02:45:32.520735	2025-10-24 02:45:32.520735	3	Mo/We/Fr	\N	25	\N	\N	The Bridges at Woodcreek Oaks	\N	\N	\N	\N	\N	\N	active	\N	\N	\N	\N	\N	\N	\N	\N
2be59463-1492-4a0c-90a1-65ac4ebc8f46	Seville	10430 Coloma Rd, Rancho Cordova, CA 95670	38.61	-121.3	commercial	1	monday	f	\N	\N	\N	t	2025-10-24 02:45:32.520706	2025-10-24 02:45:32.520706	2	Mo/Th	\N	25	\N	\N	Seville	\N	\N	\N	\N	\N	\N	active	\N	\N	\N	\N	\N	\N	\N	\N
b64eddfa-fc6e-4196-8ba1-8bd8bc3dccb8	Sierra Oaks	7640 Auburn Blvd, Citrus Heights, CA 95610	38.69	-121.24	commercial	1	tuesday	f	\N	\N	\N	t	2025-10-24 02:45:32.520709	2025-10-24 02:45:32.52071	2	Tu/Fr	\N	25	\N	\N	Sierra Oaks	\N	\N	\N	\N	\N	\N	active	\N	\N	\N	\N	\N	\N	\N	\N
313254e8-dc6d-4385-8f2a-24fbc7ae6646	SUR Apartments	2927 Marconi Ave, Sacramento, CA 95821	38.618	-121.3948	commercial	1	monday	f	\N	\N	\N	t	2025-10-24 02:45:32.520728	2025-10-24 02:45:32.520728	2	Mo/Th	\N	25	\N	\N	SUR Apartments	\N	\N	\N	\N	\N	\N	active	\N	\N	\N	\N	\N	\N	\N	\N
46accf2d-1996-4d61-a617-302dd11019cf	Village at Fair Oaks	10741 Fair Oaks Blvd, Fair Oaks, CA 95628	38.6446	-121.2722	commercial	1	monday	f	\N	\N	\N	t	2025-10-24 02:45:32.520746	2025-10-24 02:45:32.520746	2	Mo/Th	\N	25	\N	\N	Village at Fair Oaks	\N	\N	\N	\N	\N	\N	active	\N	\N	\N	\N	\N	\N	\N	\N
f4c2bdb1-bf6a-4775-9b35-fed5fcd5e3b5	Willow Glen Apartments	1625 Scarlet Ash Ave, Sacramento, CA 95834	38.6548	-121.4966	commercial	1	tuesday	f	\N	\N	\N	t	2025-10-24 02:45:32.520749	2025-10-24 02:45:32.52075	2	Tu/Fr	\N	25	\N	\N	Willow Glen Apartments	\N	\N	\N	\N	\N	\N	active	\N	\N	\N	\N	\N	\N	\N	\N
c4b28b92-26f5-4f50-8849-bc985de5794d	Wright Place	1930 Wright Place, Sacramento, CA 95825	38.61	-121.41	commercial	1	monday	f	\N	\N	\N	t	2025-10-24 02:45:32.520753	2025-10-24 02:45:32.520753	2	Mo/Th	\N	25	\N	\N	Wright Place	\N	\N	\N	\N	\N	\N	active	\N	\N	\N	\N	\N	\N	\N	\N
754ecbe5-1d00-42a2-a844-2fce6040aefc	Sierra Ridge	7434 Auburn Oaks Ct, Citrus Heights, CA 95610	38.7182	-121.2921	commercial	1	monday	f	\N	\N	\N	t	2025-10-24 02:47:33.675779	2025-10-24 02:47:33.675782	3	Mo/We/Fr	\N	25	\N	\N	Sierra Ridge	\N	\N	\N	\N	\N	\N	active	\N	\N	\N	\N	\N	\N	\N	\N
844c3150-cd6b-40f5-9e81-978b7186a9f8	Brentwood Apartments - East	2823 El Camino Ave, Sacramento, CA, 95821	38.61068	-121.396761	commercial	1	tuesday	f	\N	\N	\N	t	2025-10-24 02:45:32.520581	2025-10-25 17:23:06.854858	2	Tu/Fr	\N	25	\N	\N	Brentwood - East	\N	\N	\N	\N	\N	\N	active	\N	\N	\N	\N	\N	\N	\N	\N
7c7f7d85-2bac-4e1a-ad4d-5b57ef347b1f	Brentwood Apartments - West	2823 El Camino Ave, Sacramento, CA, 95821	38.61068	-121.396761	commercial	1	monday	f	\N	\N	\N	t	2025-10-24 02:45:32.520587	2025-10-25 17:26:22.514504	2	Mo/Th	\N	25	\N	\N	Brentwood - West	\N	\N	\N	\N	\N	\N	active	\N	\N	\N	\N	\N	\N	\N	\N
eded3825-c4da-4c2a-a61f-4a8c56a675ea	Brookside	4849 Manzanita Ave, Carmichael, CA, 95608	38.6528	-121.3286	commercial	1	tuesday	f	\N	\N	\N	t	2025-10-24 02:45:32.520593	2025-10-25 17:26:23.401793	2	Tu/Fr	\N	25	\N	\N	Brookside	\N	\N	\N	\N	\N	BLVD	active	\N	\N	\N	\N	\N	\N	\N	\N
5d81d2f5-713b-491c-abd1-96cd1758e1e1	Arbor Ridge I	4407 Oakhollow Dr, Sacramento, CA	38.6760654	-121.3633913	commercial	1	tuesday	f	\N	\N	\N	t	2025-10-24 02:45:32.52055	2025-10-25 17:35:28.221744	2	Tu/Fr	5faf9beb-86f7-4f5c-9be2-865f46836215	25	\N	\N	Arbor Ridge I	\N	\N	\N	\N	\N	BLVD	active	\N	\N	\N	\N	\N	\N	\N	\N
d87e80a5-65af-4e31-bb60-0a71af15514f	Arbor Ridge II	4440 Oakhollow Dr, Sacramento, CA	38.6758234	-121.3631422	commercial	1	monday	f	\N	\N	\N	t	2025-10-24 02:45:32.52056	2025-10-25 17:35:29.205452	2	Mo/Th	5faf9beb-86f7-4f5c-9be2-865f46836215	25	\N	\N	Arbor Ridge II	\N	\N	\N	\N	\N	BLVD	active	\N	\N	\N	\N	\N	\N	\N	\N
603a300d-3d60-4b5d-b3cd-db0cbac21728	Arden Park	2452 Wyda Way, Sacramento, CA 95825	38.6528	-121.38	commercial	1	tuesday	f	\N	\N	\N	t	2025-10-24 02:45:32.520565	2025-10-24 02:45:32.520565	2	Tu/Fr	\N	25	\N	\N	Arden Park	\N	\N	\N	\N	\N	\N	active	\N	\N	\N	\N	\N	\N	\N	\N
c4a81774-da89-42a1-bacf-b18ddeee6c8a	Auburn Village	3610 Auburn Blvd, Sacramento, CA	38.6380467	-121.3803791	commercial	1	monday	f	\N	\N	\N	t	2025-10-24 02:45:32.520575	2025-10-25 17:35:30.549636	2	Mo/Th	28e669ac-f113-42e3-affa-59d98dae5972	25	\N	\N	Auburn Village	\N	\N	\N	\N	\N	Westcal	active	\N	\N	\N	\N	\N	\N	\N	\N
03352d8c-9f92-42ae-b231-faf2725b19a4	Cottage Meadows	4146 Madison Ave, North Highlands, CA	38.6609	-121.378	commercial	1	monday	f	\N	\N	\N	t	2025-10-24 02:45:32.520601	2025-10-25 17:36:34.593617	2	Mo/Th	28e669ac-f113-42e3-affa-59d98dae5972	25	\N	\N	Cottage Meadows	\N	\N	\N	\N	\N	BLVD	active	\N	\N	\N	\N	\N	\N	\N	\N
b049a401-1821-4b97-ac5b-c036ce7fc581	Creekside Estates	6380 Denton Way, Citrus Heights, CA	38.6827083	-121.2754819	commercial	1	tuesday	f	\N	\N	\N	t	2025-10-24 02:45:32.520612	2025-10-25 17:36:34.921099	2	Tu/Fr	28e669ac-f113-42e3-affa-59d98dae5972	25	\N	\N	Creekside Estates	\N	\N	\N	\N	\N	Westcal	active	\N	\N	\N	\N	\N	\N	\N	\N
ea9fc526-fb8e-4d40-9597-849f8031dc8a	Kensington House	2440 Cottage Way, Sacramento, CA 95825	38.624	-121.4	commercial	1	monday	f	\N	\N	\N	t	2025-10-24 02:45:32.520629	2025-10-24 02:45:32.520629	2	Mo/Th	\N	25	\N	\N	Kensington House	\N	\N	\N	\N	\N	\N	active	\N	\N	\N	\N	\N	\N	\N	\N
bff101fc-c736-4e2c-b762-92d926ed7202	La Loma Terrace	2590 Capitales Dr, Rancho Cordova, CA 95670	38.59	-121.3	commercial	1	tuesday	f	\N	\N	\N	t	2025-10-24 02:45:32.520634	2025-10-24 02:45:32.520635	2	Tu/Fr	\N	25	\N	\N	La Loma Terrace	\N	\N	\N	\N	\N	\N	active	\N	\N	\N	\N	\N	\N	\N	\N
15263546-7f50-4f93-abe5-bf5e739e7297	Madison Pines	5725 Main Ave, Orangevale, CA 95662	38.6707	-121.2032	commercial	1	monday	f	\N	\N	\N	t	2025-10-24 02:45:32.520654	2025-10-24 02:45:32.520654	2	Mo/Th	\N	25	\N	\N	Madison Pines	\N	\N	\N	\N	\N	\N	active	\N	\N	\N	\N	\N	\N	\N	\N
413f2ae8-edf5-4af4-9a8d-567965460272	Morningside Creek - Bell	410 Bell Ave, Sacramento, CA 95838	38.63	-121.45	commercial	1	tuesday	f	\N	\N	\N	t	2025-10-24 02:45:32.520658	2025-10-24 02:45:32.520658	2	Tu/Fr	\N	25	\N	\N	Morningside Creek - Bell	\N	\N	\N	\N	\N	\N	active	\N	\N	\N	\N	\N	\N	\N	\N
7f320581-f304-488a-b119-24a098d73983	Pinebrook Village	7900 Auburn-Folsom Blvd, Folsom, CA, 95608	38.67	-121.2	commercial	1	monday	f	\N	\N	\N	t	2025-10-24 02:45:32.520676	2025-10-25 16:26:29.819002	2	Mo/Th	\N	25	\N	\N	Pinebrook Village	\N	\N	\N	\N	\N	\N	active	\N	\N	\N	\N	\N	\N	\N	\N
5bb3afac-9eeb-4281-9f9b-21451cc7007c	Oakridge	5242 College Oak Dr, Sacramento, CA, 95841	38.6617196	-121.3504231	commercial	1	monday	f	\N	\N	\N	t	2025-10-24 02:45:32.520665	2025-10-25 16:28:15.100192	2	Mo/Th	\N	25	\N	\N	Oakridge	\N	\N	\N	\N	\N	\N	active	\N	\N	\N	\N	\N	\N	\N	\N
970239eb-8f95-4b4b-9fa2-d509293146e3	Del Norte Park	4314 Robertson Ave, Sacramento, CA, 95821	38.6211311	-121.363914	commercial	1	monday	f	\N	\N	\N	t	2025-10-24 02:45:32.520618	2025-10-25 17:26:26.78209	2	Mo/Th	\N	25	\N	\N	Del Norte Park	\N	\N	\N	\N	\N	Westcal	active	\N	\N	\N	\N	\N	\N	\N	\N
491f4cde-bd42-4adb-a7c5-fe466628b128	Parkwood Square	2699 Darwin St, Sacramento, CA	38.614522	-121.417726	commercial	1	monday	f	\N	\N	\N	t	2025-10-24 02:45:32.520672	2025-10-26 17:59:07.592418	2	Mo/Th	28e669ac-f113-42e3-affa-59d98dae5972	25	\N	\N	Parkwood Square	\N	\N	\N	\N	\N	\N	active	\N	\N	\N	\N	\N	\N	\N	\N
20dd2005-b87f-430d-9508-5bb5f3d13655	Hurley South	2330 Hurley Way, Sacramento, CA, 95825	38.588732	-121.408933	commercial	1	monday	f	\N	\N	\N	t	2025-10-24 02:45:32.520624	2025-10-26 18:02:30.394322	2	Mo/Th	28e669ac-f113-42e3-affa-59d98dae5972	25	\N	\N	Hurley South	\N	\N	\N	\N	\N	\N	active	\N	\N	\N	\N	\N	\N	\N	\N
77e937ea-9d01-4f14-9b19-e1365a38a81d	Plumwood	2020 Wright St, Sacramento, CA, 95825	38.6023283	-121.4058895	commercial	1	monday	f	\N	\N	\N	t	2025-10-24 02:45:32.52068	2025-10-26 18:02:31.625861	2	Mo/Th	28e669ac-f113-42e3-affa-59d98dae5972	25	\N	\N	Plumwood	\N	\N	\N	\N	\N	\N	active	\N	\N	\N	\N	\N	\N	\N	\N
7932ad8c-46ec-4b32-b272-3bb4649b8002	Pointe on Bell	1630 Bell St, Sacramento, CA, 95825	38.5947809	-121.4105983	commercial	1	monday	f	\N	\N	\N	t	2025-10-24 02:45:32.520683	2025-10-26 18:02:32.544327	2	Mo/Th	28e669ac-f113-42e3-affa-59d98dae5972	25	\N	\N	Pointe on Bell	\N	\N	\N	\N	\N	\N	active	\N	\N	\N	\N	\N	\N	\N	\N
719cdf9a-d5f2-42bb-9364-72510d11930f	Riverfront (Kidney)	5953 Riverside Blvd, Sacramento, CA, 95821	38.5204966	-121.5225012	commercial	1	monday	f	\N	\N	\N	t	2025-10-24 02:45:32.520694	2025-10-26 18:02:35.526683	2	Mo/Th	28e669ac-f113-42e3-affa-59d98dae5972	25	\N	\N	Riverfront (Kidney)	\N	\N	\N	\N	\N	\N	active	\N	\N	\N	\N	\N	\N	\N	\N
b110e48f-ed80-46c0-af7d-2bf35fc011ca	Riverfront (Main Circular Pool)	5953 Riverside Blvd, Sacramento, CA, 95821	38.5204966	-121.5225012	commercial	1	monday	f	\N	\N	\N	t	2025-10-24 02:45:32.520691	2025-10-26 18:02:36.486493	2	Mo/Th	28e669ac-f113-42e3-affa-59d98dae5972	25	\N	\N	Riverfront (Main Circular Pool)	\N	\N	\N	\N	\N	\N	active	\N	\N	\N	\N	\N	\N	\N	\N
5fb84ccc-9599-4a2b-8810-bee45d793e75	Rivergate	501 Rivergate Way, Sacramento, CA, 95821	38.49616	-121.54313	commercial	1	monday	f	\N	\N	\N	t	2025-10-24 02:45:32.520698	2025-10-26 18:02:37.550429	2	Mo/Th	28e669ac-f113-42e3-affa-59d98dae5972	25	\N	\N	Rivergate	\N	\N	\N	\N	\N	\N	active	\N	\N	\N	\N	\N	\N	\N	\N
45ada20c-21e8-4419-bb51-3391cd861b54	Morningside Creek - Norwood	4412 Norwood Ave., Sacramento, CA 95838	38.63	-121.45	commercial	1	monday	f	\N	\N	\N	t	2025-10-24 02:45:32.520661	2025-10-24 02:45:32.520662	2	Mo/Th	\N	25	\N	\N	Morningside Creek - Norwood	\N	\N	\N	\N	\N	\N	active	\N	\N	\N	\N	\N	\N	\N	\N
8c923e0e-7285-4af5-8b47-3485e4fe13e6	Oak Plaza Apartment	2512 Edison Ave, Sacramento, CA 95821	38.6265	-121.4031	commercial	1	tuesday	f	\N	\N	\N	t	2025-10-24 02:45:32.520669	2025-10-24 02:45:32.520669	2	Tu/Fr	\N	25	\N	\N	Oak Plaza Apartment	\N	\N	\N	\N	\N	\N	active	\N	\N	\N	\N	\N	\N	\N	\N
b0aadbe0-9d95-4edf-984e-66996636522e	Redwood Square	4400 Elkhorn Blvd, Sacramento, CA 95824	38.5	-121.43	commercial	1	tuesday	f	\N	\N	\N	t	2025-10-24 02:45:32.520687	2025-10-24 02:45:32.520687	2	Tu/Fr	\N	25	\N	\N	Redwood Square	\N	\N	\N	\N	\N	\N	active	\N	\N	\N	\N	\N	\N	\N	\N
dc24b474-5b22-4dc7-8159-f64b3cdf6f22	San Juan HOA	5829 San Juan Ave, Citrus Heights, CA 95610	38.7	-121.28	commercial	1	tuesday	f	\N	\N	\N	t	2025-10-24 02:45:32.520702	2025-10-24 02:45:32.520702	2	Tu/Fr	\N	25	\N	\N	San Juan HOA	\N	\N	\N	\N	\N	\N	active	\N	\N	\N	\N	\N	\N	\N	\N
308cf4ec-a1c6-45c4-987f-daeceaa59fb2	Behrman Riley	4586 Minnesota Ave, Fair Oaks, CA 95628	38.6446	-121.2722	residential	1	thursday	f	\N	\N	\N	t	2025-10-24 02:25:27.897704	2025-10-25 16:09:54.721219	1	\N	\N	15	Riley	Behrman	Behrman, Riley	\N	\N	\N	\N	\N	\N	active	\N	\N	\N	\N	\N	\N	\N	\N
2e41137f-f709-4c29-9cad-ece7a3b5138c	\N	5201 Bellwood Way, Carmichael, CA, 95608	38.65	-121.32	residential	1	tuesday	f	\N	\N	\N	t	2025-10-24 02:25:27.897694	2025-10-26 12:49:44.653183	1	\N	\N	15	Murat & Rebecca	Alptekin	Alptekin, Murat & Rebecca	\N	\N	\N	\N	\N	\N	active	\N	\N	\N	\N	\N	\N	\N	\N
3966aea9-b22f-4085-83bd-14c7814f5c17	Hood Eric	4618 Shatesbury Court, Carmichael, CA 95608	38.65	-121.32	residential	1	tuesday	f	\N	\N	\N	t	2025-10-24 02:25:27.897734	2025-10-25 16:09:54.721221	1	\N	\N	15	Eric	Hood	Hood, Eric	\N	\N	\N	\N	\N	\N	active	\N	\N	\N	\N	\N	\N	\N	\N
41c2719a-7e55-49f2-b283-0a581e4ee7f3	Anderson Lisa	5300 Cabodi C Court, Fair Oaks, CA 95628	38.6446	-121.2722	residential	1	thursday	f	\N	\N	\N	t	2025-10-24 02:25:27.897696	2025-10-25 16:09:54.721222	1	\N	\N	15	Lisa	Anderson	Anderson, Lisa	\N	\N	\N	\N	\N	\N	active	\N	\N	\N	\N	\N	\N	\N	\N
449e2b9d-cd0f-4237-840c-d1ab0772bcf2	Hallissy Jim	6116 Kifisia Way, Fair Oaks, CA 95628	38.66	-121.19	residential	1	thursday	f	\N	\N	\N	t	2025-10-24 02:25:27.897726	2025-10-25 16:09:54.721222	1	\N	\N	15	Jim	Hallissy	Hallissy, Jim	\N	\N	\N	\N	\N	\N	active	\N	\N	\N	\N	\N	\N	\N	\N
536e6de3-fb44-4035-abeb-f512167dcade	Castaneda Hector	4236 Marl Way, Carmichael, CA 95608	38.64	-121.23	residential	1	tuesday	f	\N	\N	\N	t	2025-10-24 02:25:27.897709	2025-10-25 16:09:54.721223	1	\N	\N	15	Hector	Castaneda	Castaneda, Hector	\N	\N	\N	\N	\N	\N	active	\N	\N	\N	\N	\N	\N	\N	\N
5c234e36-088f-4394-b9cf-755b8767606f	Becker Herman & Donna	7918 Willowridge Court, Fair Oaks, CA 95628	38.6446	-121.2722	residential	1	tuesday	f	\N	\N	\N	t	2025-10-24 02:25:27.897701	2025-10-25 16:09:54.721223	1	\N	\N	15	Herman & Donna	Becker	Becker, Herman & Donna	\N	\N	\N	\N	\N	\N	active	\N	\N	\N	\N	\N	\N	\N	\N
62445afe-afd8-477b-bba3-51481c27a22a	Granados Cindy & Ricardo	228 La Purissima Way, Sacramento, CA 95819	38.5758	-121.4789	residential	1	wednesday	f	\N	\N	\N	t	2025-10-24 02:25:27.897721	2025-10-25 16:09:54.721223	1	\N	\N	15	Cindy & Ricardo	Granados	Granados, Cindy & Ricardo	\N	\N	\N	\N	\N	\N	active	\N	\N	\N	\N	\N	\N	\N	\N
8a8a61d0-bc5c-4514-81e8-c4cebc441e50	Contreras Monica and Carlos	4049 Wycombe Drive, Sacramento, CA 95864	38.5757266	-121.3699274	residential	1	wednesday	f	\N	\N	\N	t	2025-10-24 02:25:27.897711	2025-10-25 16:09:54.721224	1	\N	\N	15	Monica and Carlos	Contreras	Contreras, Monica and Carlos	\N	\N	\N	\N	\N	\N	active	\N	\N	\N	\N	\N	\N	\N	\N
a046bdb5-5e21-4cf9-ad8b-23dce99572ba	Landau Kenneth & Whitney Victoria	4436 Winding Way, Arden-Arcade, CA 95841	38.6008	-121.377	residential	1	wednesday	f	\N	\N	\N	t	2025-10-24 02:25:27.897739	2025-10-25 16:09:54.721224	1	\N	\N	15	Kenneth & Whitney Victoria	Landau	Landau, Kenneth & Whitney Victoria	\N	\N	\N	\N	\N	\N	active	\N	\N	\N	\N	\N	\N	\N	\N
a4f3711e-4ac3-4a06-9e9e-0289df2a7e34	Hallsten Michelle	3380 Sierra Oaks Lane, Sacramento, CA 95864	38.6	-121.38	residential	1	wednesday	f	\N	\N	\N	t	2025-10-24 02:25:27.897729	2025-10-25 16:09:54.721225	1	\N	\N	15	Michelle	Hallsten	Hallsten, Michelle	\N	\N	\N	\N	\N	\N	active	\N	\N	\N	\N	\N	\N	\N	\N
a7c3578e-14dd-4002-a6bb-c8961f85cd4d	Honore Erik	3686 Fair Oaks Blvd, Sacramento, CA 95864	38.5736	-121.3781	residential	1	wednesday	f	\N	\N	\N	t	2025-10-24 02:25:27.897731	2025-10-25 16:09:54.721225	1	\N	\N	15	Erik	Honore	Honore, Erik	\N	\N	\N	\N	\N	\N	active	\N	\N	\N	\N	\N	\N	\N	\N
c4160fb1-9c17-4f36-8456-7216293bfbe1	Cooper David	15 Peacock Gap Court, Sacramento, CA 95831	38.4930714	-121.531999	residential	1	thursday	f	\N	\N	\N	t	2025-10-24 02:25:27.897714	2025-10-25 16:09:54.721225	1	\N	\N	15	David	Cooper	Cooper, David	\N	\N	\N	\N	\N	\N	active	\N	\N	\N	\N	\N	\N	\N	\N
cefd09d5-12c0-4983-b0da-453635f72d26	Balent Tory	2713 Panay Court, Carmichael, CA 95608	38.64	-121.24	residential	1	wednesday	f	\N	\N	\N	t	2025-10-24 02:25:27.897699	2025-10-25 16:09:54.721226	1	\N	\N	15	Tory	Balent	Balent, Tory	\N	\N	\N	\N	\N	\N	active	\N	\N	\N	\N	\N	\N	\N	\N
d920c76e-d6e1-4001-9fd1-b6235a65cbd3	Blomquist Marla	8456 Rick Mary Court, Fair Oaks, CA 95628	38.6429	-121.2462	residential	1	thursday	f	\N	\N	\N	t	2025-10-24 02:25:27.897706	2025-10-25 16:09:54.721227	1	\N	\N	15	Marla	Blomquist	Blomquist, Marla	\N	\N	\N	\N	\N	\N	active	\N	\N	\N	\N	\N	\N	\N	\N
e00ae177-ebb3-43b5-bd14-c008d187a174	Haberman Murray	870 Los Molinos Way, Sacramento, CA 95864	38.59	-121.37	residential	1	wednesday	f	\N	\N	\N	t	2025-10-24 02:25:27.897724	2025-10-25 16:09:54.721228	1	\N	\N	15	Murray	Haberman	Haberman, Murray	\N	\N	\N	\N	\N	\N	active	\N	\N	\N	\N	\N	\N	\N	\N
ee00df8d-6757-4163-94b4-2991a73b6f0f	Gannon Drew	7740 Doneva Ave, Fair Oaks, CA 95628	38.6446	-121.2722	residential	1	tuesday	f	\N	\N	\N	t	2025-10-24 02:25:27.897716	2025-10-25 16:09:54.721228	1	\N	\N	15	Drew	Gannon	Gannon, Drew	\N	\N	\N	\N	\N	\N	active	\N	\N	\N	\N	\N	\N	\N	\N
23af2ece-a1d9-4da1-a091-3c0fad51d315	Pratt Robert	9201 Fieldwood Lane, Fair Oaks, CA 95628	38.6446	-121.2722	residential	1	thursday	f	\N	\N	\N	t	2025-10-24 02:25:27.897766	2025-10-25 16:09:54.721217	1	\N	\N	15	Robert	Pratt	Pratt, Robert	\N	\N	\N	\N	\N	\N	active	\N	\N	\N	\N	\N	\N	\N	\N
2be94193-dc75-4e49-91ef-4987f5c81e74	Tubis Stuart	8373 Hidden Valley Circle, Fair Oaks, CA 95628	38.66	-121.2	residential	1	tuesday	f	\N	\N	\N	t	2025-10-24 02:25:27.897774	2025-10-25 16:09:54.721219	1	\N	\N	15	Stuart	Tubis	Tubis, Stuart	\N	\N	\N	\N	\N	\N	active	\N	\N	\N	\N	\N	\N	\N	\N
3469632f-4fd9-409d-adc2-d4c9f563af55	Reed Marty	721 Crocker Road, Sacramento, CA 95864	38.5758	-121.4789	residential	1	wednesday	f	\N	\N	\N	t	2025-10-24 02:25:27.897769	2025-10-25 16:09:54.72122	1	\N	\N	15	Marty	Reed	Reed, Marty	\N	\N	\N	\N	\N	\N	active	\N	\N	\N	\N	\N	\N	\N	\N
851e1cb9-6a7d-4a50-92de-ed4e675b569c	Nazifi Nelou	8420 Lakehaven Court, Fair Oaks, CA 95628	38.6446	-121.2722	residential	1	thursday	f	\N	\N	\N	t	2025-10-24 02:25:27.897762	2025-10-25 16:09:54.721223	1	\N	\N	15	Nelou	Nazifi	Nazifi, Nelou	\N	\N	\N	\N	\N	\N	active	\N	\N	\N	\N	\N	\N	\N	\N
9c9b45ed-fe89-4355-bd97-acac723cf77b	Miller Scott	4925 Cameron Ranch Drive, Carmichael, CA 95608	38.65	-121.32	residential	1	tuesday	f	\N	\N	\N	t	2025-10-24 02:25:27.897759	2025-10-25 16:09:54.721224	1	\N	\N	15	Scott	Miller	Miller, Scott	\N	\N	\N	\N	\N	\N	active	\N	\N	\N	\N	\N	\N	\N	\N
ade2501f-9acb-4113-9428-a67519d927bd	Marois Michael	6080 Shirley Ave, Carmichael, CA 95608	38.65	-121.32	residential	1	wednesday	f	\N	\N	\N	t	2025-10-24 02:25:27.897749	2025-10-25 16:09:54.721225	1	\N	\N	15	Michael	Marois	Marois, Michael	\N	\N	\N	\N	\N	\N	active	\N	\N	\N	\N	\N	\N	\N	\N
c738c677-5847-444f-8fa2-7559cfe6cfba	Stillens Jim	3100 Cowan Circle, Sacramento, CA 95821	38.6236	-121.3854	residential	1	wednesday	f	\N	\N	\N	t	2025-10-24 02:25:27.897771	2025-10-25 16:09:54.721226	1	\N	\N	15	Jim	Stillens	Stillens, Jim	\N	\N	\N	\N	\N	\N	active	\N	\N	\N	\N	\N	\N	\N	\N
cbdcd2bc-82f1-4982-a51e-a734b5da1285	Mayo Joan	5923 Courville Court, Fair Oaks, CA 95628	38.6429	-121.2462	residential	1	thursday	f	\N	\N	\N	t	2025-10-24 02:25:27.897754	2025-10-25 16:09:54.721226	1	\N	\N	15	Joan	Mayo	Mayo, Joan	\N	\N	\N	\N	\N	\N	active	\N	\N	\N	\N	\N	\N	\N	\N
d73eeda4-fd97-4dd2-9045-26afe83490c8	Matullo Otto & Mindy	143 Carmody Circle, Folsom, CA 95630	38.6672	-121.1482	residential	1	tuesday	f	\N	\N	\N	t	2025-10-24 02:25:27.897752	2025-10-25 16:09:54.721227	1	\N	\N	15	Otto & Mindy	Matullo	Matullo, Otto & Mindy	\N	\N	\N	\N	\N	\N	active	\N	\N	\N	\N	\N	\N	\N	\N
d97f940f-f005-4fed-8202-e77a209c2a4d	McHugh Gavin	1005 Fountain Drive, West Sacramento, CA 95605	38.575	-121.5248	residential	1	thursday	f	\N	\N	\N	t	2025-10-24 02:25:27.897757	2025-10-25 16:09:54.721227	1	\N	\N	15	Gavin	McHugh	McHugh, Gavin	\N	\N	\N	\N	\N	\N	active	\N	\N	\N	\N	\N	\N	\N	\N
fa3a07ca-18e4-4bd6-8585-7c6fdca68dfb	Perrilloux RJ	9437 Winding River Way, Elk Grove, CA 95624	38.41	-121.37	residential	1	tuesday	f	\N	\N	\N	t	2025-10-24 02:25:27.897764	2025-10-25 16:09:54.721229	1	\N	\N	15	RJ	Perrilloux	Perrilloux, RJ	\N	\N	\N	\N	\N	\N	active	\N	\N	\N	\N	\N	\N	\N	\N
\.


--
-- Data for Name: drivers; Type: TABLE DATA; Schema: public; Owner: routeoptimizer
--

COPY public.drivers (id, name, email, phone, start_location_address, start_latitude, start_longitude, end_location_address, end_latitude, end_longitude, working_hours_start, working_hours_end, max_customers_per_day, is_active, notes, created_at, updated_at, color) FROM stdin;
28e669ac-f113-42e3-affa-59d98dae5972	Shane	\N	\N	9412 Winding River Way, Elk Grove, CA 95624	38.4167398	-121.3422038	9412 Winding River Way, Elk Grove, CA 95624	38.4167398	-121.3422038	09:00:00	17:00:00	15	t	\N	2025-10-24 01:57:05.656425	2025-10-24 01:57:05.656427	#3498db
5faf9beb-86f7-4f5c-9be2-865f46836215	Chance	\N	\N	4849 Manzanita Ave, Carmichael, CA 95608	38.617127	-121.3282843	4849 Manzanita Ave, Carmichael, CA 95608	38.617127	-121.3282843	09:00:00	17:00:00	15	t	\N	2025-10-24 01:54:49.332884	2025-10-25 12:24:42.762	#2ecc71
\.


--
-- Data for Name: route_stops; Type: TABLE DATA; Schema: public; Owner: routeoptimizer
--

COPY public.route_stops (id, route_id, customer_id, sequence, estimated_arrival_time, estimated_service_duration, estimated_drive_time_from_previous, estimated_distance_from_previous, created_at) FROM stdin;
\.


--
-- Data for Name: routes; Type: TABLE DATA; Schema: public; Owner: routeoptimizer
--

COPY public.routes (id, driver_id, service_day, total_duration_minutes, total_distance_miles, total_customers, optimization_algorithm, optimization_score, created_at, updated_at) FROM stdin;
\.


--
-- Name: alembic_version alembic_version_pkc; Type: CONSTRAINT; Schema: public; Owner: routeoptimizer
--

ALTER TABLE ONLY public.alembic_version
    ADD CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num);


--
-- Name: customers customers_pkey; Type: CONSTRAINT; Schema: public; Owner: routeoptimizer
--

ALTER TABLE ONLY public.customers
    ADD CONSTRAINT customers_pkey PRIMARY KEY (id);


--
-- Name: drivers drivers_pkey; Type: CONSTRAINT; Schema: public; Owner: routeoptimizer
--

ALTER TABLE ONLY public.drivers
    ADD CONSTRAINT drivers_pkey PRIMARY KEY (id);


--
-- Name: route_stops route_stops_pkey; Type: CONSTRAINT; Schema: public; Owner: routeoptimizer
--

ALTER TABLE ONLY public.route_stops
    ADD CONSTRAINT route_stops_pkey PRIMARY KEY (id);


--
-- Name: routes routes_pkey; Type: CONSTRAINT; Schema: public; Owner: routeoptimizer
--

ALTER TABLE ONLY public.routes
    ADD CONSTRAINT routes_pkey PRIMARY KEY (id);


--
-- Name: ix_customers_display_name; Type: INDEX; Schema: public; Owner: routeoptimizer
--

CREATE INDEX ix_customers_display_name ON public.customers USING btree (display_name);


--
-- Name: ix_customers_id; Type: INDEX; Schema: public; Owner: routeoptimizer
--

CREATE INDEX ix_customers_id ON public.customers USING btree (id);


--
-- Name: ix_customers_service_day; Type: INDEX; Schema: public; Owner: routeoptimizer
--

CREATE INDEX ix_customers_service_day ON public.customers USING btree (service_day);


--
-- Name: ix_customers_service_type; Type: INDEX; Schema: public; Owner: routeoptimizer
--

CREATE INDEX ix_customers_service_type ON public.customers USING btree (service_type);


--
-- Name: ix_drivers_id; Type: INDEX; Schema: public; Owner: routeoptimizer
--

CREATE INDEX ix_drivers_id ON public.drivers USING btree (id);


--
-- Name: ix_drivers_name; Type: INDEX; Schema: public; Owner: routeoptimizer
--

CREATE INDEX ix_drivers_name ON public.drivers USING btree (name);


--
-- Name: ix_route_stops_customer_id; Type: INDEX; Schema: public; Owner: routeoptimizer
--

CREATE INDEX ix_route_stops_customer_id ON public.route_stops USING btree (customer_id);


--
-- Name: ix_route_stops_id; Type: INDEX; Schema: public; Owner: routeoptimizer
--

CREATE INDEX ix_route_stops_id ON public.route_stops USING btree (id);


--
-- Name: ix_route_stops_route_id; Type: INDEX; Schema: public; Owner: routeoptimizer
--

CREATE INDEX ix_route_stops_route_id ON public.route_stops USING btree (route_id);


--
-- Name: ix_routes_created_at; Type: INDEX; Schema: public; Owner: routeoptimizer
--

CREATE INDEX ix_routes_created_at ON public.routes USING btree (created_at);


--
-- Name: ix_routes_driver_id; Type: INDEX; Schema: public; Owner: routeoptimizer
--

CREATE INDEX ix_routes_driver_id ON public.routes USING btree (driver_id);


--
-- Name: ix_routes_id; Type: INDEX; Schema: public; Owner: routeoptimizer
--

CREATE INDEX ix_routes_id ON public.routes USING btree (id);


--
-- Name: ix_routes_service_day; Type: INDEX; Schema: public; Owner: routeoptimizer
--

CREATE INDEX ix_routes_service_day ON public.routes USING btree (service_day);


--
-- Name: customers customers_assigned_driver_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: routeoptimizer
--

ALTER TABLE ONLY public.customers
    ADD CONSTRAINT customers_assigned_driver_id_fkey FOREIGN KEY (assigned_driver_id) REFERENCES public.drivers(id);


--
-- Name: route_stops route_stops_customer_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: routeoptimizer
--

ALTER TABLE ONLY public.route_stops
    ADD CONSTRAINT route_stops_customer_id_fkey FOREIGN KEY (customer_id) REFERENCES public.customers(id) ON DELETE CASCADE;


--
-- Name: route_stops route_stops_route_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: routeoptimizer
--

ALTER TABLE ONLY public.route_stops
    ADD CONSTRAINT route_stops_route_id_fkey FOREIGN KEY (route_id) REFERENCES public.routes(id) ON DELETE CASCADE;


--
-- Name: routes routes_driver_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: routeoptimizer
--

ALTER TABLE ONLY public.routes
    ADD CONSTRAINT routes_driver_id_fkey FOREIGN KEY (driver_id) REFERENCES public.drivers(id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--

\unrestrict WDclYOfgXgob3ktolVSQoLgVg4fLHcUW72YRIwWSGgebdmoNvodTyEAlbIqbH6V

