from datetime import UTC, datetime

from grad_engine import filters, sponsorship

CYCLES = ["Class of 2027", "Class of 2026"]


class TestNewGrad:
    def test_matches_new_grad_wording(self):
        for title in (
            "Software Engineer, New Grad",
            "2026 University Graduate - Software Engineer",
            "Early Career Software Engineer",
            "Entry Level Developer",
            "Software Engineer - Class of 2027",
            "Rotational Program - Software Engineering",
            "Associate Software Engineer",
            "Junior Data Analyst",
            "Software Engineer I",
            "Software Engineer 1",
        ):
            assert filters.is_new_grad(title), title

    def test_rejects_substring_false_positive(self):
        # "internal" / "international" must not read as internships (and so
        # must not veto a real new grad title)...
        assert filters.is_new_grad("Internal Tools Engineer, New Grad")
        assert filters.is_new_grad("International Payments Software Engineer I")
        # ...and neither word is itself new grad evidence.
        assert not filters.is_new_grad("Internal Tools Engineer")
        assert not filters.is_new_grad("International Operations")

    def test_rejects_internship_family_titles(self):
        for title in (
            "Software Engineer Intern",
            "Data Co-op",
            "Software Engineering Internship, New Grad",
            "Software Apprentice",
            "Fellowship - New Grad Software Engineer",
            "Coding Bootcamp New Grad",
            "MBA Associate",
        ):
            assert not filters.is_new_grad(title), title

    def test_rejects_senior(self):
        assert not filters.is_new_grad("Senior Software Engineer")
        assert not filters.is_new_grad("Lead New Grad Engineer")

    def test_rejects_levels_above_one(self):
        for title in ("Software Engineer II", "New Grad Software Engineer II",
                      "SWE L4", "Data Scientist - Level 2"):
            assert not filters.is_new_grad(title), title

    def test_bare_role_title_is_not_evidence(self):
        assert not filters.is_new_grad("Software Engineer")
        assert not filters.is_new_grad("")

    def test_cooperative_education_is_a_coop_program(self):
        assert not filters.is_new_grad("Cooperative Education Software Developer")


class TestTech:
    def test_keeps_software_and_ml(self):
        assert filters.is_tech("Software Engineer Intern")
        assert filters.is_tech("Machine Learning Intern")
        assert filters.is_tech("Backend Developer Intern")

    def test_drops_non_tech_and_hardware(self):
        assert not filters.is_tech("Mechanical Engineering Intern")
        assert not filters.is_tech("Technical Recruiting Intern")
        assert not filters.is_tech("FPGA Hardware Intern")

    def test_keeps_phd(self):
        # PhD is not excluded here: a PhD new grad research role is in scope.
        assert filters.is_tech("Research Scientist, New Grad (PhD)")
        assert filters.is_tech("PhD Machine Learning Engineer, University Graduate")

    def test_overloaded_mobile_and_programming_words_are_not_tech(self):
        assert not filters.is_tech(
            "2027 ETP Intern - Corporate Banking Group, Commercial Credit "
            "Products, Mobile, AL"
        )
        assert not filters.is_tech(
            "Current Programming Intern, Sony Pictures Television - Fall 2026"
        )

    def test_mobile_and_programming_keep_explicit_software_context(self):
        for title in (
            "Mobile Application Engineer Intern",
            "iOS Mobile Developer Intern",
            "Computer Programming Intern",
            "Software Programming Intern",
        ):
            assert filters.is_tech(title), title

    def test_verified_technical_role_families_are_kept(self):
        for title in (
            "Quantitative Research Intern",
            "Quant Research Intern",
            "Quantitative Trading Intern",
            "Cloud Engineer Intern",
            "Database Engineer Intern",
            "DevSecOps Intern",
        ):
            assert filters.is_tech(title), title

    def test_software_first_hardware_titles_are_kept(self):
        assert filters.is_tech("Embedded Software / Hardware Intern")
        assert filters.is_tech("Firmware Engineering Intern - Electrical Systems")
        assert not filters.is_tech("Electrical Hardware Engineering Intern")


class TestSeason:
    def test_explicit_cycle(self):
        assert filters.detect_season(
            "Software Engineer, New Grad (2027)", CYCLES) == "Class of 2027"
        assert filters.detect_season(
            "2026 University Graduate - Data Scientist", CYCLES) == "Class of 2026"

    def test_year_only_maps_to_cycle(self):
        assert filters.detect_season(
            "2027 Software Engineer, New Grad", CYCLES) == "Class of 2027"

    def test_undated_is_dropped(self):
        assert filters.detect_season("Software Engineer, New Grad", CYCLES) is None

    def test_off_cycle_is_dropped(self):
        assert filters.detect_season("Class of 2025 Software Engineer", CYCLES) is None
        assert filters.detect_season("New Grad Software Engineer 2029", CYCLES) is None

    def test_apostrophe_short_year(self):
        assert filters.detect_season(
            "Software Engineer I - Class of '27", CYCLES) == "Class of 2027"
        assert filters.detect_season("New Grad '26 Data Analyst", CYCLES) == "Class of 2026"

    def test_graduation_year_in_title_is_the_cycle(self):
        # Inverted from the internship tracker: "Class of 2027" names the
        # graduating class, which is exactly what this list tracks.
        assert filters.detect_season(
            "Software Engineer (Class of 2027)", CYCLES) == "Class of 2027"
        assert filters.detect_season(
            "SWE New Grad - Graduating 2026", CYCLES) == "Class of 2026"

    def test_term_word_is_just_its_year(self):
        # No term logic in titles: "Fall 2026" is simply the year 2026.
        assert filters.detect_season(
            "Software Engineer, New Grad - Fall 2026", CYCLES) == "Class of 2026"
        assert filters.detect_season(
            "New Grad Software Engineer (Start Summer 2027)", CYCLES) == "Class of 2027"

    def test_is_cycle_label(self):
        assert filters.is_cycle_label("Class of 2026")
        assert filters.is_cycle_label("Class of 2031")
        assert not filters.is_cycle_label("Summer 2027")
        assert not filters.is_cycle_label("Unspecified")
        assert not filters.is_cycle_label("")
        assert not filters.is_cycle_label(None)

    def test_cycle_label_and_year_round_trip(self):
        assert filters.cycle_label(2027) == "Class of 2027"
        assert filters.cycle_label("2026") == "Class of 2026"
        assert filters.cycle_year("Class of 2027") == 2027
        assert filters.cycle_year(filters.NOT_STATED) is None
        assert filters.cycle_year("Summer 2027") is None

    def test_default_cycles_are_the_two_tracked_classes(self):
        assert filters.detect_season("New Grad SWE 2027") == "Class of 2027"
        assert filters.detect_season("New Grad SWE 2026") == "Class of 2026"
        assert filters.detect_season("New Grad SWE 2028") is None

    def test_year_range_states_both_cycles_primary_follows_cycles_order(self):
        assert filters.detect_season(
            "Quant Developer, New Grad - 2026/2027", CYCLES) == "Class of 2027"
        assert filters.detect_season(
            "2026-2027 Information Technology - Software Engineer I", CYCLES
        ) == "Class of 2027"
        assert filters.detect_season(
            "New Grad Software Engineer (2026/2027)", ("Class of 2026", "Class of 2027")
        ) == "Class of 2026"

    def test_requisition_ids_are_not_years(self):
        for title in ("New Grad Software Engineer (JR-2026-0042)",
                      "New Grad Software Engineer 2026-12345",
                      "New Grad Software Engineer #2026123"):
            assert filters.detect_season(title, CYCLES) is None, title
            assert not filters.states_explicit_year(title), title

    def test_states_explicit_year(self):
        assert filters.states_explicit_year("2025 New Grad Software Engineer")
        assert filters.states_explicit_year("Software Engineer, New Grad (2027)")
        assert not filters.states_explicit_year("Software Engineer I")

    def test_year_is_matched_as_a_word(self):
        assert filters.detect_season(
            "2027 Software Engineer - Springfield Platform", ("Class of 2027",)
        ) == "Class of 2027"

    def test_company_history_years_in_a_title_are_not_cycles(self):
        assert filters.detect_season(
            "New Grad Software Engineer - Founded 2026 Startup", CYCLES) is None


class TestRegion:
    def test_us_match(self):
        assert filters.region_ok("San Francisco, CA", want_us=True, want_canada=False)
        assert filters.region_ok("New York, United States", want_us=True, want_canada=False)

    def test_canada_excluded_when_us_only(self):
        assert not filters.region_ok("Toronto, Ontario, Canada", want_us=True, want_canada=False)
        assert filters.region_ok("Toronto, Ontario, Canada", want_us=False, want_canada=True)

    def test_country_code_prefix_not_us(self):
        # "DE-Berlin" is Germany, not the Delaware state code
        assert not filters.region_ok("DE-Berlin-Trion", want_us=True, want_canada=False)

    def test_named_foreign_country_beats_state_code_lookalike(self):
        # "IN - Bangalore, India" is India, not Indiana
        assert not filters.is_united_states("IN - Bangalore, India")
        assert not filters.is_united_states("Munich, Germany")
        assert not filters.is_united_states("CA - Sydney, Australia")

    def test_explicit_us_token_wins_for_multi_country_strings(self):
        assert filters.is_united_states("New York, USA; Bangalore, India")

    def test_multi_location_order_never_hides_a_valid_us_option(self):
        forward = "Austin, TX; London, United Kingdom"
        reverse = "London, United Kingdom; Austin, TX"
        assert filters.is_united_states(forward)
        assert filters.is_united_states(reverse)
        assert filters.region_ok(forward, want_us=True, want_canada=False)

    def test_state_code_with_spaced_suffix_still_us(self):
        assert filters.is_united_states("Dallas, TX - Headquarters")

    def test_other_americas_are_not_us(self):
        assert not filters.is_united_states("Remote - Latin America")
        assert not filters.is_united_states("South America")
        # "North America" remains US-eligible (US-inclusive remote regions).
        assert filters.is_united_states("Remote (North America)")

    def test_canada_vetoes_state_code_lookalike(self):
        # The Magna leak: "Milton, Ontario, CA" read the trailing CA as
        # California. A province name / "Canada" beats a bare state code…
        assert not filters.is_united_states("Milton, Ontario, CA")
        assert not filters.is_united_states("Toronto, ON, Canada")
        # …but a full US state name still wins ("Ontario, California" is a
        # real US city), and explicit US tokens are untouched.
        assert filters.is_united_states("Ontario, California")
        assert filters.is_united_states("Ontario, CA")
        assert filters.is_united_states("Ontario, California, United States")

    def test_city_names_containing_usa_are_not_us(self):
        # The Medtronic leak: "usa" was matched as a SUBSTRING, so every city
        # spelling those three letters in a row read as the United States and
        # foreign roles landed in a US-only list.
        assert not filters.is_united_states("Lausanne, Vaud, Switzerland")
        assert not filters.is_united_states("Jerusalem, Israel")
        assert not filters.is_united_states("Busan, South Korea")
        assert not filters.is_united_states("Syracuse, Sicily, Italy")
        # …while the same letters as a real token still count, and a US city
        # that merely contains them keeps its state code.
        assert filters.is_united_states("Sausalito, CA")
        assert filters.is_united_states("Syracuse, New York")

    def test_us_country_token_spellings(self):
        for loc in ("United States", "United States of America", "USA",
                    "U.S.A.", "U.S.", "Remote - US", "New York, NY, USA"):
            assert filters.is_united_states(loc), loc

    def test_more_foreign_countries_are_excluded(self):
        for loc in ("London, England", "Edinburgh, Scotland", "Kyiv, Ukraine",
                    "Vilnius, Lithuania", "Zagreb, Croatia", "Amman, Jordan",
                    "Quito, Ecuador", "Kathmandu, Nepal"):
            assert not filters.is_united_states(loc), loc

    def test_new_england_is_not_read_as_foreign(self):
        # "England" hides inside "New England" — a US region.
        assert filters.is_united_states("Cambridge, MA (New England)")

    def test_foreign_country_names_can_be_us_city_components(self):
        for loc in (
            "Lebanon, NH",
            "Lebanon, New Hampshire",
            "Mexico, MO",
            "Poland, OH",
            "Peru, IN",
            "Panama City, FL",
            "China, ME",
            "India, TX",
            "Canadian, TX",
        ):
            assert filters.is_united_states(loc), loc
            assert not filters.is_canada(loc), loc

    def test_georgia_country_needs_us_corroboration(self):
        assert not filters.is_united_states("Tbilisi, Georgia")
        assert filters.is_united_states("Atlanta, Georgia")
        assert filters.is_united_states("Tbilisi, Georgia, USA")

    def test_structured_state_codes_are_case_insensitive(self):
        assert filters.is_united_states("Austin, tx")
        assert filters.is_united_states("San Francisco, ca")


class TestMultiCycle:
    """One requisition can genuinely hire for two graduating classes."""

    CYCLES = ("Class of 2027", "Class of 2026")

    def test_both_stated_cycles_are_returned(self):
        # Stored as Class of 2027 only, the Class of 2026 section would never
        # show a role that literally says 2026.
        title = "Software Engineer, New Grad (2026/2027)"
        assert filters.detect_seasons(title, self.CYCLES) == [
            "Class of 2027", "Class of 2026",
        ]

    def test_single_cycle_returns_one(self):
        assert filters.detect_seasons(
            "Software Engineer, New Grad (2027)", self.CYCLES) == ["Class of 2027"]

    def test_untracked_cycles_are_not_returned(self):
        assert filters.detect_seasons("New Grad, Class of 2028", self.CYCLES) == []

    def test_yearless_title_returns_nothing(self):
        # detect_seasons never infers.
        assert filters.detect_seasons("Software Engineer, New Grad", self.CYCLES) == []

    def test_tracked_cycle_survives_an_untracked_neighbour(self):
        # "2026 / 2028": the tracked half must not be dropped as off-cycle
        # just because its neighbour is untracked.
        assert filters.detect_season(
            "New Grad 2026 / 2028 Software Engineer", self.CYCLES) == "Class of 2026"


class TestProgramType:
    def test_labels_are_the_five_program_types(self):
        assert filters.PROGRAM_TYPES == (
            "New Grad", "Early Career", "Entry Level", "Rotational",
            "Junior / Associate",
        )

    def test_new_grad_titles(self):
        for title in ("Software Engineer, New Grad", "University Graduate - SWE",
                      "Software Engineer - Class of 2027", "Recent Graduate Data Analyst"):
            assert filters.program_type(title) == "New Grad", title

    def test_each_other_label(self):
        assert filters.program_type("Early Career Software Engineer") == "Early Career"
        assert filters.program_type("Entry Level Developer") == "Entry Level"
        assert filters.program_type("Technology Rotational Program") == "Rotational"
        assert filters.program_type("Associate Software Engineer") == "Junior / Associate"
        assert filters.program_type("Junior Data Analyst") == "Junior / Associate"

    def test_level_one_title_reads_as_new_grad(self):
        assert filters.program_type("Software Engineer I") == "New Grad"

    def test_explicit_graduate_wording_wins(self):
        assert filters.program_type("Associate Software Engineer (New Grad)") == "New Grad"
        assert filters.program_type("Early Career Rotational Program, New Grad") == "New Grad"

    def test_precedence_after_graduate_wording(self):
        # Rotational > Early Career > Entry Level > Junior / Associate.
        assert filters.program_type("Early Career Rotational Program") == "Rotational"
        assert filters.program_type("Early Career Entry Level Engineer") == "Early Career"
        assert filters.program_type("Entry Level Junior Developer") == "Entry Level"


class TestRemote:
    def test_remote_locations(self):
        for loc in ("Remote", "Remote - US", "Austin, TX (Remote)", "US Remote"):
            assert filters.is_remote(loc), loc

    def test_onsite_locations(self):
        for loc in ("New York, NY", "Austin, TX", "", "Seattle, Washington"):
            assert not filters.is_remote(loc), loc

    def test_remote_sensing_is_a_field_of_study_not_a_work_mode(self):
        assert not filters.is_remote("Pasadena, CA", "Remote Sensing Software Intern")
        assert filters.is_remote("Pasadena, CA", "Software Intern (Remote)")


class TestCategory:
    def test_categories(self):
        assert filters.categorize("Software Engineer Intern") == "Software"
        assert filters.categorize("Machine Learning Intern") == "Data & ML/AI"
        assert filters.categorize("Cybersecurity Intern") == "Security"


class TestCycleUnstatedOk:
    """Recency gate for roles nobody stated a cycle for.

    This replaced `infer_season`, which guessed a cycle (defaulting to Summer)
    from the posting month. Measured against the live list that guess was
    confirmed by the posting text 0 times out of 60 and contradicted every
    time it was checkable, so the guess is gone. Only the recency test — the
    part that was actually sound — remains.
    """

    NOW = datetime(2026, 7, 15, tzinfo=UTC)

    def _ok(self, title, posted, **kw):
        return filters.cycle_unstated_ok(title, posted, now=self.NOW, **kw)

    def test_recent_yearless_role_is_kept(self):
        assert self._ok("Software Engineer Intern", "2026-07-10")

    def test_term_word_alone_does_not_invent_a_cycle(self):
        # "Summer Intern" names a term but no year. It used to become
        # "Summer 2027"; now it is simply kept as cycle-unstated.
        assert self._ok("Summer Intern - Backend", "2026-07-01")
        assert self._ok("Fall Software Intern", "2026-07-01")

    def test_stale_posting_is_dropped(self):
        # 60 days old with a 45-day trust window -> evergreen sludge.
        assert not self._ok("Software Engineer Intern", "2026-05-01")

    def test_wider_window_accepts_older(self):
        assert self._ok("Software Engineer Intern", "2026-05-01", max_age_days=90)

    def test_no_posted_date_is_dropped(self):
        assert not self._ok("Software Engineer Intern", None)

    def test_explicit_offcycle_year_is_refused(self):
        # "Summer 2026 Intern" was refused by detect_season for a reason — it
        # must not sneak back in through the unstated lane.
        assert not self._ok("Summer 2026 Intern: Cyber Security", "2026-07-10")
        assert not self._ok("Fall 2027 Software Intern", "2026-07-10")

    def test_explicit_year_never_reaches_this_gate(self):
        # Belt and suspenders: detect_season handles dated titles first.
        assert filters.detect_season(
            "Software Engineer, New Grad 2027", CYCLES) == "Class of 2027"

    def test_not_stated_is_not_a_cycle_label(self):
        # Anything treating it as a cycle would re-introduce the fake claim.
        assert not filters.is_cycle_label(filters.NOT_STATED)
        assert filters.NOT_STATED not in CYCLES


class TestTechScopeExclusions:
    def test_non_tech_roles_with_ai_bait_excluded(self):
        assert not filters.is_tech("Digital Marketer Intern-Align AI")
        assert not filters.is_tech("Account Management AI Intern")
        assert not filters.is_tech("Unpaid Programming Intern")

    def test_real_tech_titles_still_pass(self):
        assert filters.is_tech("Programming Intern")
        assert filters.is_tech("AI Software Engineer Intern")


class TestSeasonFromText:
    NOW = datetime(2026, 7, 15, tzinfo=UTC)

    def _stated(self, text, **kw):
        return filters.season_from_text(text, now=self.NOW, **kw)

    def test_class_of_phrase(self):
        assert self._stated("This role is open to the Class of 2027.") == "Class of 2027"
        assert self._stated("Candidates from the Class of '27 welcome.") == "Class of 2027"

    def test_class_of_list_returns_every_class_latest_first(self):
        for text in ("We are hiring the class of 2026 or 2027.",
                     "Classes of 2026 and 2027 welcome."):
            assert filters.seasons_from_text(text, now=self.NOW) == [
                "Class of 2027", "Class of 2026"], text
            assert self._stated(text) is None, text

    def test_graduation_sentence(self):
        for text in ("Expected graduation date: May 2027.",
                     "Degree conferred by June 2027.",
                     "Must be completing a bachelor's degree by May 2027."):
            assert self._stated(text) == "Class of 2027", text

    def test_conflicting_mentions_never_override(self):
        # Grad-window boilerplate lists several terms -> no verdict.
        assert self._stated(
            "Internship candidates enrolled between Fall 2026 and Summer 2027 "
            "are encouraged to apply."
        ) is None

    def test_far_away_mention_ignored(self):
        pad = "x " * 200
        assert self._stated(
            f"Our company was named a best employer of Summer 2026. {pad} "
            "This internship is fully remote."
        ) is None

    def test_empty_text(self):
        assert self._stated("") is None

    def test_start_date_names_the_class(self):
        # The Doctors Without Borders case, as a full-time start date.
        assert self._stated(
            "ESTIMATED START DATE: Anticipated start date for July 2026. "
            "DURATION: full-time."
        ) == "Class of 2026"
        assert self._stated("Start date: summer 2027.") == "Class of 2027"
        assert self._stated("Join us in August 2027 in Austin.") == "Class of 2027"

    def test_graduation_range_states_both_classes(self):
        text = "Candidates graduating between December 2026 and June 2027."
        assert filters.seasons_from_text(text, now=self.NOW) == [
            "Class of 2027", "Class of 2026"]
        assert self._stated(text) is None

    def test_graduation_month_is_the_class(self):
        # The Fortive case, inverted: for a new grad role the graduation
        # window IS the class year.
        assert self._stated(
            "Currently pursuing a BS in Computer Science. Graduating "
            "December 2026 or later. Strong understanding of networks."
        ) == "Class of 2026"

    def test_company_history_dates_ignored(self):
        # The Nio case: "Founded in November 2014" is company history — killed
        # by both the plausible-year window and the context guard.
        assert self._stated(
            "Founded in November 2014, our internship program pairs you with "
            "senior researchers."
        ) is None

    def test_two_class_graduation_window_abstains(self):
        # The Palantir case: two graduating classes are both returned by
        # seasons_from_text, so the single-verdict reader abstains.
        text = "Must be planning on graduating in Winter 2027 or Spring 2028."
        assert filters.seasons_from_text(text, now=self.NOW) == [
            "Class of 2028", "Class of 2027"]
        assert self._stated(text) is None

    def test_degree_window_month_mentions_are_guarded(self):
        # The Datasite case: a degree window phrased with months.
        assert self._stated(
            "Bachelor's degree in CS, Engineering or Data Science preferrably "
            "between May and August 2026. This is a 10-12 week internship."
        ) is None

    def test_implausible_year_ignored(self):
        assert self._stated(
            "Our internship program has run every summer since May 2019."
        ) is None

    def test_unrelated_degree_or_company_words_do_not_veto_a_real_cycle(self):
        for text, expected in (
            (
                "Students pursuing a degree can join our Class of 2027 program.",
                "Class of 2027",
            ),
            (
                "Founded in 2010, Acme is hiring the Class of 2027.",
                "Class of 2027",
            ),
            (
                "Established in Boston, our Class of 2026 program starts soon.",
                "Class of 2026",
            ),
        ):
            assert self._stated(text) == expected

    def test_year_before_graduation_word_counts(self):
        assert self._stated("2026 graduates may apply for this role.") == "Class of 2026"
        assert self._stated(
            "December 2026 graduates are eligible for this role.") == "Class of 2026"

    def test_start_year_can_follow_other_words(self):
        assert self._stated(
            "Starting in 2027, you will join the platform team.") == "Class of 2027"
        assert self._stated(
            "Our cohort for 2027 is accepting applications.") == "Class of 2027"

    def test_multiple_classes_are_returned_latest_first_without_guessing_one(self):
        text = "You will start in 2026 or 2027."
        assert filters.seasons_from_text(text, now=self.NOW) == [
            "Class of 2027", "Class of 2026"]
        assert self._stated(text) is None

    def test_two_terms_sharing_one_year_are_one_class(self):
        text = "This new grad role starts in Fall/Winter 2026."
        assert filters.seasons_from_text(text, now=self.NOW) == ["Class of 2026"]
        assert self._stated(text) == "Class of 2026"

    def test_founded_never_counts(self):
        assert self._stated("Founded in 2026, Acme hires new grads each year.") is None
        assert self._stated("Founded in 2012, Acme builds databases.") is None

    def test_past_tense_graduation_never_counts(self):
        assert self._stated("Candidates who graduated in 2019 with a BS.") is None
        assert self._stated("Candidates who graduated in 2025 need not apply.") is None

    def test_plausibility_window_is_last_year_through_two_years_out(self):
        # NOW is 2026: plausible classes are 2025..2028.
        assert self._stated("Expected graduation: May 2024.") is None
        assert self._stated("Expected graduation: May 2025.") == "Class of 2025"
        assert self._stated("Graduating in 2028.") == "Class of 2028"
        assert self._stated("Graduating in 2031.") is None

    def test_implausible_class_of_year_is_ignored(self):
        # Tier 1 must apply the same window as the other tiers.
        assert filters.seasons_from_text("Class of 2031 candidates.", now=self.NOW) == []
        assert filters.seasons_from_text(
            "Class of 2031 alumni mentor you. Expected graduation: May 2027.",
            now=self.NOW,
        ) == ["Class of 2027"]
class TestSeasonEvidencePriority:
    """The strongest evidence tier wins; weaker tiers are not consulted.

    A posting that says "Class of 2027" and, later, "graduating in December
    2026" names its class outright; the graduation sentence must not turn
    that into a two-class disagreement. Likewise a graduation sentence
    outranks a start date.
    """

    NOW = datetime(2026, 7, 15, tzinfo=UTC)

    def _stated(self, text):
        return filters.season_from_text(text, now=self.NOW)

    def test_class_of_beats_a_graduation_sentence(self):
        assert self._stated(
            "Class of 2027. Candidates graduating in December 2026 are also welcome."
        ) == "Class of 2027"

    def test_graduation_beats_a_start_sentence(self):
        assert self._stated(
            "Start date: summer 2027. You must be graduating by December 2026."
        ) == "Class of 2026"

    def test_start_sentence_still_works_when_nothing_else_is_stated(self):
        assert self._stated("This role starts in June 2027.") == "Class of 2027"

    def test_genuinely_conflicting_stated_terms_still_abstain(self):
        # Two different stated cycles = real ambiguity; abstain rather than
        # pick one. (Multi-cycle titles are handled by detect_seasons.)
        text = ("Summer 2027 internship. We also run a Winter 2027 internship "
                "program on the same team.")
        assert self._stated(text) is None

    def test_no_internship_context_is_ignored(self):
        assert self._stated("The company was founded in Fall 2026.") is None


class TestStripHtmlOrdering:
    """Entity-encoded markup has to be decoded before tags can be stripped.

    Greenhouse returns `&lt;p&gt;Fall 2026...`. Stripping tags first found no
    `<` to match, and the later unescape turned the entities back into live
    tags — so every classifier downstream (season, skills, pay, sponsorship)
    was reading angle brackets as if they were prose.
    """

    def test_entity_encoded_markup_is_stripped(self):
        raw = "&lt;p&gt;&lt;strong&gt;Fall 2026 Internship:&lt;/strong&gt;Durham, NC.&lt;/p&gt;"
        out = sponsorship.strip_html(raw)
        assert "<" not in out and ">" not in out
        assert out.startswith("Fall 2026 Internship:")

    def test_plain_markup_is_still_stripped(self):
        out = sponsorship.strip_html("<p><b>Summer 2027</b> internship</p>")
        assert out == "Summer 2027 internship"

    def test_season_survives_the_round_trip(self):
        raw = ("&lt;p&gt;&lt;strong&gt;Class of 2026 Software Engineer:&lt;/strong&gt; "
               "Expected graduation between December 2025 and May 2026.&lt;/p&gt;")
        text = sponsorship.strip_html(raw)
        assert filters.season_from_text(
            text, now=datetime(2026, 7, 15, tzinfo=UTC)) == "Class of 2026"


class TestDetectSeasonsYears:
    """detect_seasons reads years (ranges, short years), never requisition ids."""

    C = ("Class of 2027", "Class of 2026")

    def test_year_need_not_be_adjacent_to_program_words(self):
        assert filters.detect_seasons(
            "New Grad 2027 - Software Developer", self.C) == ["Class of 2027"]
        assert filters.detect_seasons(
            "2027 Software Engineer, New Grad", self.C) == ["Class of 2027"]

    def test_year_ranges_state_both_classes(self):
        for title in ("New Grad Software Engineer (2026/2027)",
                      "New Grad Software Engineer (2026 - 2027)",
                      "Software Engineer, New Grad 2026-27",
                      "New Grad Software Engineer 2026 or 2027",
                      "New Grad SWE 2026 & 2027"):
            assert filters.detect_seasons(title, self.C) == [
                "Class of 2027", "Class of 2026"], title

    def test_a_split_dual_cycle_title_keeps_both_halves(self):
        assert filters.detect_seasons(
            "New Grad 2027 / Class of 2026", self.C
        ) == ["Class of 2027", "Class of 2026"]

    def test_short_years_are_read(self):
        assert filters.detect_seasons("New Grad SWE '27", self.C) == ["Class of 2027"]
        assert filters.detect_seasons(
            "Class of \u201926 Software Engineer", self.C) == ["Class of 2026"]

    def test_requisition_ids_are_not_years(self):
        for title in ("New Grad Software Engineer (JR-2026-0042)",
                      "New Grad Software Engineer 2026-12345",
                      "New Grad Software Engineer #2026123",
                      "New Grad SWE R2026-001"):
            assert filters.detect_seasons(title, self.C) == [], title
        assert filters.detect_seasons(
            "Software Engineer, New Grad (2027) JR-2026-0042", self.C
        ) == ["Class of 2027"]

    def test_graduation_years_are_cycles(self):
        assert filters.detect_seasons("SWE, Class of 2027", self.C) == ["Class of 2027"]

    def test_untracked_cycles_are_excluded(self):
        for t in ("Class of 2025 New Grad", "New Grad Software Engineer 2028"):
            assert filters.detect_seasons(t, self.C) == [], t


class TestRealRunFalsePositives:
    """Patterns the first live run let through (2026-09-28)."""

    def test_grocery_front_end_is_not_tech(self):
        assert not filters.is_tech("Front End Entry Level")
        assert not filters.is_tech("Back End Associate")

    def test_front_end_with_an_engineering_word_is_tech(self):
        assert filters.is_tech("Front End Engineer, New Grad")
        assert filters.is_tech("Frontend Developer (Entry Level)")
        assert filters.is_tech("Back-End Software Engineer I")
        assert filters.is_tech("Front End / Back End Developer")

    def test_level_range_spanning_mid_levels_is_not_new_grad(self):
        assert not filters.is_new_grad("Software Engineer 1/2")
        assert not filters.is_new_grad("Software Engineer 1/2/3 (Hybrid)")
        assert not filters.is_new_grad("Software Engineer I/II")
        assert filters.is_new_grad("Software Engineer 1")
