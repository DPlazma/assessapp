"""
Arbor MIS API client.

Uses GraphQL for reads, REST for writes.
Auth: Basic Authentication (app_username + api_key).
"""

import logging
from urllib.parse import urljoin

import requests
from requests.auth import HTTPBasicAuth

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 30


class ArborClient:
    """Wrapper around the Arbor REST + GraphQL APIs."""

    def __init__(self, base_url, app_username, api_key):
        base = base_url.rstrip("/")
        self.rest_url = f"{base}/rest-v2"
        self.graphql_url = f"{base}/graphql/query"
        self.auth = HTTPBasicAuth(app_username, api_key)
        self.session = requests.Session()
        self.session.auth = self.auth
        self.session.headers.update({"Accept": "application/json"})

    # ── GraphQL reads ──────────────────────────────────────────────

    def graphql(self, query, variables=None):
        """Execute a GraphQL query and return the data dict.

        Automatically retries once on 429 (Too Many Requests).
        """
        import time

        payload = {"query": query}
        if variables:
            payload["variables"] = variables

        for attempt in range(3):
            resp = self.session.post(
                self.graphql_url,
                json=payload,
                timeout=DEFAULT_TIMEOUT,
            )
            if resp.status_code == 429:
                wait = 10 * (attempt + 1)
                logger.info("GraphQL 429, waiting %ds…", wait)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            body = resp.json()
            if "errors" in body:
                raise ArborAPIError(f"GraphQL errors: {body['errors']}")
            return body.get("data", {})

        resp.raise_for_status()
        return {}

    # ── REST reads ─────────────────────────────────────────────────

    def rest_get(self, path, params=None):
        """GET a REST resource. Path is relative to rest_url."""
        url = f"{self.rest_url}/{path.lstrip('/')}"
        resp = self.session.get(url, params=params, timeout=DEFAULT_TIMEOUT)
        resp.raise_for_status()
        return resp.json()

    # ── REST writes ────────────────────────────────────────────────

    def rest_post(self, path, data):
        """POST (create) a REST resource."""
        url = f"{self.rest_url}/{path.lstrip('/')}"
        resp = self.session.post(url, json=data, timeout=DEFAULT_TIMEOUT)
        resp.raise_for_status()
        return resp.json()

    def rest_put(self, path, data):
        """PUT (update) a REST resource."""
        url = f"{self.rest_url}/{path.lstrip('/')}"
        resp = self.session.put(url, json=data, timeout=DEFAULT_TIMEOUT)
        resp.raise_for_status()
        return resp.json()

    # ── Convenience: test connection ───────────────────────────────

    def test_connection(self):
        """
        Test that credentials work by fetching students.
        Returns (True, message) or (False, error_message).
        """
        try:
            data = self.graphql("{ Student { id leavingDate } }")
            students = data.get("Student", [])
            current = [s for s in students if not s.get("leavingDate")]
            return True, f"Connected — {len(current)} current students ({len(students)} total inc. leavers)."
        except Exception as e:
            return False, str(e)

    # ── Discovery helpers ──────────────────────────────────────────

    def fetch_students(self):
        """Fetch current students with UPN for matching."""
        data = self.graphql("""
            { Student { id displayName upn legalFirstName legalLastName leavingDate } }
        """)
        return [s for s in data.get("Student", []) if not s.get("leavingDate")]

    def fetch_assessments(self):
        """Fetch assessments configured in Arbor."""
        data = self.graphql("""
            { Assessment { id assessmentName assessmentShortName
                           subject { id displayName } } }
        """)
        return data.get("Assessment", [])

    def fetch_grade_sets(self):
        """Fetch grade sets and their grades."""
        data = self.graphql("""
            { GradeSet { id displayName
                         grades { id shortName longName gradeValue gradeOrder } } }
        """)
        return data.get("GradeSet", [])

    def fetch_measurement_periods(self):
        """Fetch progress measurement periods (terms)."""
        data = self.graphql("""
            { ProgressMeasurementPeriod {
                id periodName shortName startDate endDate
                academicYear { id displayName }
              } }
        """)
        return data.get("ProgressMeasurementPeriod", [])

    # ── Write: push assessment mark ────────────────────────────────

    def push_assessment_mark(self, student_href, assessment_href,
                             period_href, grade_href, assessment_date):
        """
        Create a StudentProgressAssessmentMark in Arbor via REST POST.

        All *_href params are Arbor REST hrefs like
        '/rest-v2/students/123'.
        """
        payload = {
            "request": {
                "studentProgressAssessmentMark": {
                    "student": {
                        "entityType": "Student",
                        "href": student_href,
                    },
                    "assessment": {
                        "entityType": "Assessment",
                        "href": assessment_href,
                    },
                    "progressMeasurementPeriod": {
                        "entityType": "ProgressMeasurementPeriod",
                        "href": period_href,
                    },
                    "grade": {
                        "entityType": "Grade",
                        "href": grade_href,
                    },
                    "assessmentDate": assessment_date,
                }
            }
        }
        return self.rest_post("student-progress-assessment-marks", payload)

    # ── Import helpers (read from Arbor → AssessApp) ───────────────

    def fetch_academic_years(self):
        """Fetch academic years from Arbor."""
        data = self.graphql("""
            { AcademicYear { id displayName startDate endDate } }
        """)
        return data.get("AcademicYear", [])

    def fetch_students_full(self):
        """Fetch current students with names, UPN, DOB, and class."""
        data = self.graphql("""
            { Student {
                id upn displayName
                legalFirstName legalLastName leavingDate
                person { dateOfBirth }
                registrationForm { displayName id }
            } }
        """)
        return [s for s in data.get("Student", []) if not s.get("leavingDate")]

    def fetch_registration_forms(self):
        """Fetch registration forms / tutor groups (Arbor's class groups)."""
        data = self.graphql("""
            { RegistrationForm {
                id displayName
                academicYear { id displayName }
            } }
        """)
        return data.get("RegistrationForm", [])

    def fetch_staff(self, include_inactive=False):
        """Fetch current staff members.

        Filters on Arbor's ``isActiveInSchool`` flag, which is more
        reliable than ``leavingDate`` (some leavers never have a
        leavingDate set but are flagged inactive instead).
        """
        data = self.graphql("""
            { Staff {
                id displayName leavingDate isActiveInSchool
                person { legalFirstName legalLastName }
            } }
        """)
        staff = data.get("Staff", [])
        if include_inactive:
            return staff
        return [
            s for s in staff
            if s.get("isActiveInSchool") and not s.get("leavingDate")
        ]

    def fetch_staff_class_links(self):
        """Fetch which staff are linked to which registration forms.

        Uses the 'tutors' relationship on RegistrationForm which returns
        assigned teachers per form.  Returns one dict per staff-form pair.
        """
        data = self.graphql("""
            { RegistrationForm {
                id displayName
                tutors { id displayName
                         person { legalFirstName legalLastName } }
            } }
        """)
        links = []
        for form in data.get("RegistrationForm", []):
            form_ref = {"id": form.get("id"), "displayName": form.get("displayName")}
            for tutor in (form.get("tutors") or []):
                links.append({
                    "registrationForm": form_ref,
                    "staff": tutor,
                })
        return links

    # ── Timetable-based TA discovery (REST) ────────────────────────

    def _batch_rest_fetch(self, ids, path_template, entity_key,
                          workers=6, batch_size=40, delay=1.5):
        """Fetch multiple REST resources by ID in concurrent batches.

        Uses standalone ``requests.get`` (not the shared session) so
        each thread gets its own connection — avoids pool-exhaustion
        problems that surfaced during large concurrent fetches.

        Returns ``{id: parsed_entity_dict, ...}`` for successful fetches.
        """
        import time
        from concurrent.futures import ThreadPoolExecutor, as_completed

        results = {}
        base = self.rest_url
        auth = self.auth

        def _fetch_one(resource_id):
            try:
                url = f"{base}/{path_template.format(id=resource_id)}"
                resp = requests.get(
                    url, auth=auth,
                    headers={"Accept": "application/json"},
                    timeout=DEFAULT_TIMEOUT,
                )
                if resp.status_code == 200:
                    return resource_id, resp.json().get(entity_key)
            except Exception:
                pass
            return resource_id, None

        for i in range(0, len(ids), batch_size):
            batch = ids[i:i + batch_size]
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = [pool.submit(_fetch_one, rid) for rid in batch]
                for f in as_completed(futures):
                    rid, data = f.result()
                    if data:
                        results[rid] = data
            if i + batch_size < len(ids):
                time.sleep(delay)

        return results

    def _rest_list_with_retry(self, path, list_key, retries=3, backoff=10):
        """GET a REST list endpoint with retry on 429 / transient errors."""
        import time

        for attempt in range(retries):
            try:
                resp = requests.get(
                    f"{self.rest_url}/{path}",
                    auth=self.auth,
                    headers={"Accept": "application/json"},
                    timeout=DEFAULT_TIMEOUT,
                )
                if resp.status_code == 429:
                    wait = backoff * (attempt + 1)
                    logger.info("Rate-limited on %s, waiting %ds…", path, wait)
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
                return resp.json().get(list_key, [])
            except requests.exceptions.HTTPError:
                raise  # re-raise non-429 HTTP errors
            except Exception:
                if attempt < retries - 1:
                    time.sleep(backoff)
                    continue
                raise
        return []

    def fetch_ta_class_links(self, year_id, arbor_staff=None):
        """Discover staff → class links via the Arbor timetable.

        Chain:  AcademicUnit → TimetableSlot → TimetableSlotStaff.

        Returns a list in the **same format** as
        ``fetch_staff_class_links()`` so the caller can merge both.
        Includes *all* timetabled staff (teachers + TAs); the caller
        should deduplicate against the tutor list to isolate TAs.

        If *arbor_staff* (list from ``fetch_staff()``) is supplied the
        method skips an extra GraphQL call to resolve names.
        """
        # ── 1. AcademicUnit → class map for the target year ──
        au_data = self.graphql("""
            { AcademicUnit {
                id academicUnitName
                academicYear { id }
                registrationForm { id displayName }
            } }
        """)
        au_to_class = {}
        for au in au_data.get("AcademicUnit", []):
            if str((au.get("academicYear") or {}).get("id")) != str(year_id):
                continue
            reg = au.get("registrationForm") or {}
            if reg.get("id"):
                au_to_class[int(au["id"])] = {
                    "form_id": int(reg["id"]),
                    "class_name": reg.get(
                        "displayName", au.get("academicUnitName", "")
                    ),
                }

        if not au_to_class:
            logger.info("fetch_ta: no AcademicUnits for year %s", year_id)
            return []

        logger.info(
            "fetch_ta: %d AcademicUnits for year %s",
            len(au_to_class), year_id,
        )

        # ── 2. Scan recent TimetableSlots for our AUs ──
        try:
            items = self._rest_list_with_retry(
                "timetable-slots", "timetableSlots"
            )
            all_slot_ids = sorted(int(s["id"]) for s in items)
        except Exception as e:
            logger.warning("fetch_ta: slot list failed: %s", e)
            return []

        # Only scan the tail — current-year slots are near the end
        recent_slot_ids = all_slot_ids[-500:]
        slot_details = self._batch_rest_fetch(
            recent_slot_ids, "timetable-slots/{id}", "timetableSlot",
            workers=5, batch_size=30, delay=2.0,
        )

        slot_to_class = {}
        for sid, sdata in slot_details.items():
            tobj = sdata.get("timetabledObject") or {}
            if tobj.get("entityType") != "AcademicUnit":
                continue
            au_id = tobj.get("id")
            if au_id and int(au_id) in au_to_class:
                slot_to_class[sid] = au_to_class[int(au_id)]

        if not slot_to_class:
            logger.info("fetch_ta: no slots matched target classes")
            return []

        logger.info(
            "fetch_ta: %d slots → %d classes",
            len(slot_to_class),
            len({v["form_id"] for v in slot_to_class.values()}),
        )

        # ── 3. Scan recent TimetableSlotStaff ──
        import time
        time.sleep(15)  # cooldown — Arbor rate-limits after ~500 requests

        try:
            items = self._rest_list_with_retry(
                "timetable-slot-staffs", "timetableSlotStaffs"
            )
            all_tss_ids = sorted(int(s["id"]) for s in items)
        except Exception as e:
            logger.warning("fetch_ta: TSS list failed: %s", e)
            return []

        # Only scan the tail — enough to find who is in each class
        recent_tss_ids = all_tss_ids[-1500:]
        tss_details = self._batch_rest_fetch(
            recent_tss_ids, "timetable-slot-staffs/{id}", "timetableSlotStaff",
        )

        staff_class_pairs = {}  # (staff_id, form_id) → class info
        for _tss_id, tdata in tss_details.items():
            slot_ref = tdata.get("timetableSlot") or {}
            staff_ref = tdata.get("staff") or {}
            slot_id = slot_ref.get("id")
            staff_id = staff_ref.get("id")
            if slot_id and staff_id and int(slot_id) in slot_to_class:
                info = slot_to_class[int(slot_id)]
                staff_class_pairs.setdefault(
                    (int(staff_id), info["form_id"]), info
                )

        logger.info(
            "fetch_ta: %d unique staff→class pairs", len(staff_class_pairs)
        )

        # ── 4. Resolve staff IDs to names ──
        if arbor_staff is None:
            staff_data = self.graphql("""
                { Staff {
                    id displayName leavingDate isActiveInSchool
                    person { legalFirstName legalLastName }
                } }
            """)
            arbor_staff = [
                s for s in staff_data.get("Staff", [])
                if s.get("isActiveInSchool") and not s.get("leavingDate")
            ]

        staff_by_id = {int(s["id"]): s for s in arbor_staff}

        links = []
        for (sid, fid), info in staff_class_pairs.items():
            staff = staff_by_id.get(sid)
            if not staff:
                continue
            links.append({
                "registrationForm": {
                    "id": str(info["form_id"]),
                    "displayName": info["class_name"],
                },
                "staff": staff,
            })

        logger.info("fetch_ta: returning %d links", len(links))
        return links

    def fetch_staff_roles(self):
        """Determine staff roles from Arbor contracts.

        Returns ``{int(staff_id): role}`` where *role* is one of
        ``'teacher'``, ``'ta'``, or ``'hlta'``.
        """
        data = self.graphql("""
            { Staff {
                id leavingDate isActiveInSchool
                staffContracts { displayName }
            } }
        """)
        roles = {}
        for s in data.get("Staff", []):
            if s.get("leavingDate") or not s.get("isActiveInSchool"):
                continue
            sid = int(s["id"])
            contracts = [
                c.get("displayName", "")
                for c in (s.get("staffContracts") or [])
            ]
            if any("HLTA" in c or "Higher Level" in c for c in contracts):
                roles[sid] = "hlta"
            elif any("Teaching Assistant" in c for c in contracts):
                roles[sid] = "ta"
            else:
                roles[sid] = "teacher"
        return roles


class ArborAPIError(Exception):
    """Custom exception for Arbor API errors."""
    pass


def get_arbor_client():
    """
    Build an ArborClient from the current ArborSettings.
    Returns (client, None) or (None, error_string).
    """
    from .models import ArborSettings

    cfg = ArborSettings.load()
    if not cfg.enabled:
        return None, "Arbor integration is disabled."
    if not cfg.base_url or not cfg.app_username or not cfg.api_key:
        return None, "Arbor credentials are incomplete."

    client = ArborClient(
        base_url=cfg.base_url,
        app_username=cfg.app_username,
        api_key=cfg.api_key,
    )
    return client, None
