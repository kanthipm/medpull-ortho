import Foundation

/// The JSON the tests decode. The demo routes' examples are the ones in
/// docs/dev/showcase.md, word for word; `me` and the exercise rows are what
/// a local server answered for the seeded lifter (hirt-cole), since the
/// contract says `me` is "exactly GET /api/mobile/me".
enum Fixtures {
    /// The decoder `APIClient` uses: snake_case keys become camelCase.
    static func decode<T: Decodable>(_ type: T.Type, _ json: String) throws -> T {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(type, from: Data(json.utf8))
    }

    // MARK: docs/dev/showcase.md, "The demo API"

    static let personas = """
    {
      "as_of": "2026-11-12",
      "sms": {"number": "+15049081262", "text_body": "Hi MedPull", "configured": true},
      "versions": [
        {"key": "clinic", "label": "Clinic", "blurb": "Followed by a clinic between visits",
         "orgs": [{"id": "hirt", "name": "H.I.R.T. Physical Therapy", "personas": [
           {"id": "hirt-cole", "name": "Cole Whitaker", "hero": true,
            "tagline": "Patellar tendinopathy · progressive loading",
            "detail": "Load spike, pain rising",
            "account_kind": "clinic", "tier": "high",
            "has": {"wearable": false, "exercises": true, "thread": true}}]}]},
        {"key": "personal", "label": "Personal", "blurb": "…", "orgs": [{"id": "personal", "name": "MedPull Personal", "personas": []}]},
        {"key": "sports", "label": "Sports", "blurb": "…", "orgs": [{"id": "rice-mbb", "name": "Rice · Men's Basketball", "personas": []}]}
      ]
    }
    """

    /// The same list as a newer or sloppier server might send it: keys this
    /// build has never heard of, a persona with only an id and a name, one
    /// with no id (unusable), a tier that is not a clinic tier, and `has`
    /// as something other than an object.
    static let personasLoose = """
    {
      "as_of": "2026-11-12",
      "filled_on": "2026-11-12",
      "versions": [
        {"key": "clinic", "orgs": [{"id": "hirt", "logo": {"url": "x"}, "personas": [
           {"id": "hirt-june", "name": "June Halvorsen"},
           {"name": "Nobody"},
           {"id": "hirt-cole", "name": "Cole Whitaker", "hero": true, "tier": null, "has": "everything", "badge": 3}
        ]}]},
        {"key": "sports", "label": "Sports", "orgs": [{"id": "rice-mbb", "name": "Rice", "personas": [
           {"id": "jalen-okoro", "name": "Jalen Okoro", "tier": "return_to_play", "account_kind": "sports",
            "has": {"wearable": true}}
        ]}]},
        {"key": "family", "label": "Family", "orgs": []}
      ]
    }
    """

    static func session(me: String = me) -> String {
        """
        {"session_token": "tok_abc123", "me": \(me), "persona": {"id": "hirt-cole", "name": "Cole Whitaker", "version": "clinic"}}
        """
    }

    static let resetDay = """
    {"reopened": 3, "removed": 2}
    """

    static let phoneWaiting = """
    {"phone": "+17135550142", "reachable": false, "text_to": "+15049081262", "text_body": "Hi MedPull", "sent": false, "detail": null}
    """

    static let phoneConnected = """
    {"phone": "+17135550142", "reachable": true, "text_to": "+15049081262", "text_body": "Hi MedPull", "sent": true, "detail": "Welcome text sent"}
    """

    static let phoneUnbound = """
    {"phone": null, "reachable": false, "text_to": "+15049081262", "text_body": "Hi MedPull", "sent": false, "detail": null}
    """

    // MARK: docs/dev/showcase.md, "Links"

    static let linkInfo = """
    {"kind": "exercise", "ref_id": "40", "day": "2026-11-13", "expires_at": "2026-11-26T09:00:00",
     "signin": true, "patient": {"first_name": "Cole"}, "clinic": {"name": "H.I.R.T. Physical Therapy"},
     "app": {"scheme": "medpulldemo", "url": "medpulldemo://a/Zk3vQ9aL0pXw"}, "web": "/patient/#link=Zk3vQ9aL0pXw"}
    """

    /// A link to Today: no ref, no day, no clinic (a member has none).
    static let linkInfoBare = """
    {"kind": "today", "ref_id": null, "day": null, "expires_at": null, "signin": false,
     "patient": {"first_name": "Jordan"}, "clinic": null,
     "app": {"scheme": "medpulldemo", "url": "medpulldemo://a/x"}, "web": "/patient/#link=x"}
    """

    static func linkSession(me: String = me, target: String = #"{"kind": "task", "ref_id": 912, "day": null}"#) -> String {
        """
        {"session_token": "tok_link", "me": \(me), "target": \(target)}
        """
    }

    // MARK: GET /api/mobile/me, as a local server answers it for hirt-cole

    static let me = """
    {
      "patient": {
        "id": "hirt-cole", "name": "Cole Whitaker", "first_name": "Cole", "initials": "CW",
        "mode": "general", "account_kind": "clinic",
        "procedure_display": "Patellar tendinopathy · progressive loading",
        "surgery_date": null, "joined_date": "2026-10-29", "postop_day": null, "days_enrolled": 14,
        "care_pathway": "Patellar tendinopathy · progressive loading",
        "phone_masked": null, "email": null,
        "hospital": {"id": "hirt", "name": "H.I.R.T. Physical Therapy", "system": "Rise Gym", "city": "Tomball", "state": "TX"},
        "care_team": [{"name": "Dr. Sean Harris", "role": "pt"}, {"name": "Dr. Ashley Gregg", "role": "pt"}]
      },
      "profiles": [{"patient_id": "hirt-cole", "kind": "clinic", "label": "H.I.R.T. Physical Therapy",
                    "detail": "Followed by your care team", "current": true}],
      "subscription": null,
      "sports": null,
      "consent": {"version": "2026-09-26.1", "accepted_at": "2026-11-12T02:52:07.647202",
                  "scopes": {"data_storage": true, "ai_processing": true, "research_use": true, "beta_ack": true},
                  "current_version": "2026-09-26.1", "needs_consent": false},
      "recovery": {"level": "high", "label": "Care team reviewing",
                   "blurb": "Your care team is keeping an eye on activity this week and symptoms this week.",
                   "trajectory": {"state": "unknown", "pct": null},
                   "days_with_data": 0, "days_until_full_picture": 3, "computed_at": "2026-11-12T02:56:40.467830"},
      "tasks_open": 0,
      "unread_messages": 0,
      "wearables": {"aggregator_configured": false, "connection_status": null,
                    "apple_health": {"connected": false, "last_sync_at": null},
                    "device_health": {"platform": null, "connected": false, "last_sync_at": null},
                    "devices": [], "last_data_at": null},
      "features": {"sms": false, "apple_health": false, "device_health": false, "deep_link_scheme": "medpull",
                   "beta": true, "consent_version": "2026-09-26.1", "paywall": false}
    }
    """
}
