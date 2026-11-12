import XCTest
@testable import MedPullDemo

/// The demo routes are written by other streams to the shapes in
/// docs/dev/showcase.md. These tests decode that document's own examples
/// with the app's types, so a drift between the contract and the app fails
/// here rather than in front of a room.
final class DemoContractTests: XCTestCase {
    // MARK: GET /api/demo/personas

    func testPersonasDecodeFromTheContractExample() throws {
        let roster = try Fixtures.decode(DemoRoster.self, Fixtures.personas)
        XCTAssertEqual(roster.asOf, "2026-11-12")
        XCTAssertEqual(roster.sms?.number, "+15049081262")
        XCTAssertEqual(roster.sms?.textBody, "Hi MedPull")
        XCTAssertEqual(roster.sms?.configured, true)
        XCTAssertEqual(roster.versions.map(\.key), ["clinic", "personal", "sports"])

        let clinic = try XCTUnwrap(roster.group(.clinic))
        XCTAssertEqual(clinic.label, "Clinic")
        XCTAssertEqual(clinic.blurb, "Followed by a clinic between visits")
        XCTAssertEqual(clinic.personaCount, 1)
        let org = try XCTUnwrap(clinic.orgs.first)
        XCTAssertEqual(org.id, "hirt")
        XCTAssertEqual(org.name, "H.I.R.T. Physical Therapy")

        let cole = try XCTUnwrap(org.personas.first)
        XCTAssertEqual(cole.id, "hirt-cole")
        XCTAssertEqual(cole.name, "Cole Whitaker")
        XCTAssertTrue(cole.hero)
        XCTAssertEqual(cole.tagline, "Patellar tendinopathy · progressive loading")
        XCTAssertEqual(cole.detail, "Load spike, pain rising")
        XCTAssertEqual(cole.accountKind, "clinic")
        XCTAssertEqual(cole.tier, "high")
        XCTAssertEqual(cole.has, DemoPersona.Has(wearable: false, exercises: true, thread: true))
        XCTAssertEqual(cole.initials, "CW")
        XCTAssertEqual(cole.chip?.text, "High priority")

        // The other two versions are listed with an organisation and nobody
        // in it yet: a count of zero, not a missing version.
        XCTAssertEqual(roster.group(.personal)?.personaCount, 0)
        XCTAssertEqual(roster.group(.sports)?.orgs.first?.name, "Rice · Men's Basketball")
        XCTAssertEqual(roster.org(ofPersona: "hirt-cole")?.id, "hirt")
        XCTAssertEqual(roster.persona("hirt-cole")?.name, "Cole Whitaker")
        XCTAssertNil(roster.persona("nobody"))
    }

    func testPersonasSurviveASloppierAnswer() throws {
        let roster = try Fixtures.decode(DemoRoster.self, Fixtures.personasLoose)
        XCTAssertNil(roster.sms)
        let hirt = try XCTUnwrap(roster.group(.clinic)?.orgs.first)
        // No name on the organisation: its id stands in.
        XCTAssertEqual(hirt.name, "hirt")
        // The persona with no id is dropped; the other two stay.
        XCTAssertEqual(hirt.personas.map(\.id), ["hirt-june", "hirt-cole"])
        // The hero leads whatever the server's order.
        XCTAssertEqual(hirt.ordered.map(\.id), ["hirt-cole", "hirt-june"])

        let june = hirt.personas[0]
        XCTAssertFalse(june.hero)
        XCTAssertEqual(june.tagline, "")
        XCTAssertNil(june.tier)
        XCTAssertNil(june.chip)
        XCTAssertEqual(june.has, DemoPersona.Has())
        // `has` arrived as a string: nothing is claimed.
        XCTAssertEqual(hirt.personas[1].has, DemoPersona.Has())

        let jalen = try XCTUnwrap(roster.group(.sports)?.orgs.first?.personas.first)
        XCTAssertEqual(jalen.chip?.text, "Return to play")
        XCTAssertEqual(jalen.has, DemoPersona.Has(wearable: true, exercises: false, thread: false))
        // A version this build has no tabs for is kept in the list and
        // simply never asked for.
        XCTAssertEqual(roster.versions.count, 3)
        XCTAssertNil(roster.group(.personal))
    }

    // MARK: POST /api/demo/session

    func testSessionCarriesTheTokenAndMe() throws {
        let answer = try Fixtures.decode(DemoSessionResponse.self, Fixtures.session())
        XCTAssertEqual(answer.sessionToken, "tok_abc123")
        XCTAssertEqual(answer.me.patient.id, "hirt-cole")
        XCTAssertEqual(answer.me.patient.firstName, "Cole")
        XCTAssertEqual(answer.me.patient.hospital?.name, "H.I.R.T. Physical Therapy")
        XCTAssertFalse(answer.me.needsConsent)
        XCTAssertEqual(answer.persona?.version, "clinic")
        XCTAssertEqual(DemoVersion(me: answer.me), .clinic)
    }

    func testSessionWithoutATokenIsRefused() {
        XCTAssertThrowsError(try Fixtures.decode(DemoSessionResponse.self, #"{"me": \#(Fixtures.me)}"#))
    }

    // MARK: POST /api/demo/reset-day

    func testResetDay() throws {
        let answer = try Fixtures.decode(DemoResetResponse.self, Fixtures.resetDay)
        XCTAssertEqual(answer.reopened, 3)
        XCTAssertEqual(answer.removed, 2)
        XCTAssertEqual(answer.sentence, "3 exercises reopened and 2 thread lines removed.")
        let nothing = try Fixtures.decode(DemoResetResponse.self, #"{"reopened": 0, "removed": 0}"#)
        XCTAssertEqual(nothing.sentence, "Today was already at its start: nothing to put back.")
        let one = try Fixtures.decode(DemoResetResponse.self, #"{"reopened": 1, "removed": 1}"#)
        XCTAssertEqual(one.sentence, "1 exercise reopened and 1 thread line removed.")
    }

    // MARK: GET | POST | DELETE /api/demo/phone

    func testPhoneStates() throws {
        let waiting = try Fixtures.decode(DemoPhoneState.self, Fixtures.phoneWaiting)
        XCTAssertTrue(waiting.isBound)
        XCTAssertFalse(waiting.reachable)
        XCTAssertEqual(waiting.textTo, "+15049081262")
        XCTAssertEqual(waiting.textBody, "Hi MedPull")
        XCTAssertFalse(waiting.sent)
        XCTAssertNil(waiting.detail)

        let connected = try Fixtures.decode(DemoPhoneState.self, Fixtures.phoneConnected)
        XCTAssertTrue(connected.isBound)
        XCTAssertTrue(connected.reachable)
        XCTAssertTrue(connected.sent)
        XCTAssertEqual(connected.detail, "Welcome text sent")

        let unbound = try Fixtures.decode(DemoPhoneState.self, Fixtures.phoneUnbound)
        XCTAssertFalse(unbound.isBound)
        XCTAssertNil(unbound.phone)
    }

    // MARK: GET /api/links/{token} and POST …/session

    func testLinkInfo() throws {
        let info = try Fixtures.decode(AppLinkInfo.self, Fixtures.linkInfo)
        XCTAssertEqual(info.target, AppLinkTarget(kind: "exercise", refId: "40", day: "2026-11-13"))
        XCTAssertEqual(info.target.refNumber, 40)
        XCTAssertTrue(info.signin)
        XCTAssertEqual(info.patientFirstName, "Cole")
        XCTAssertEqual(info.clinicName, "H.I.R.T. Physical Therapy")
        XCTAssertEqual(info.expiresAt, "2026-11-26T09:00:00")

        let bare = try Fixtures.decode(AppLinkInfo.self, Fixtures.linkInfoBare)
        XCTAssertEqual(bare.target, AppLinkTarget(kind: "today"))
        XCTAssertNil(bare.target.refNumber)
        XCTAssertFalse(bare.signin)
        XCTAssertNil(bare.clinicName)
    }

    func testLinkSession() throws {
        // `ref_id` as a number: the task id of a `task` or `checkin` link.
        let answer = try Fixtures.decode(AppLinkSession.self, Fixtures.linkSession())
        XCTAssertEqual(answer.sessionToken, "tok_link")
        XCTAssertEqual(answer.me.patient.id, "hirt-cole")
        XCTAssertEqual(answer.target, AppLinkTarget(kind: "task", refId: "912"))
        XCTAssertEqual(answer.target?.refNumber, 912)

        // An answer that only signs in: the GET's target is used instead.
        let plain = try Fixtures.decode(AppLinkSession.self, #"{"session_token": "t", "me": \#(Fixtures.me)}"#)
        XCTAssertNil(plain.target)
    }

    // MARK: The URLs the system hands over

    func testLinkParsing() throws {
        func link(_ raw: String) -> DemoLink? { URL(string: raw).flatMap(DemoLink.init(url:)) }
        XCTAssertEqual(link("medpulldemo://a/Zk3vQ9aL0pXw"), .token("Zk3vQ9aL0pXw"))
        XCTAssertEqual(link("https://demo.medpull.app/a/Zk3vQ9aL0pXw"), .token("Zk3vQ9aL0pXw"))
        XCTAssertEqual(link("http://localhost:8108/a/abc"), .token("abc"))
        XCTAssertEqual(link("https://demo.medpull.app/a/abc?utm=sms"), .token("abc"))
        XCTAssertEqual(link("https://demo.medpull.app/t/tasktoken"), .taskToken("tasktoken"))
        XCTAssertEqual(link("medpulldemo://t/tasktoken"), .taskToken("tasktoken"))
        XCTAssertEqual(link("medpulldemo://tasks/912"), .task(912))
        XCTAssertEqual(link("medpulldemo://exercises/40"), .exercise(40))
        XCTAssertEqual(link("MEDPULLDEMO://A/abc"), .token("abc"))
        // Not the app's: another scheme, another path, a path with no token.
        XCTAssertNil(link("medpull://tasks/912"))
        XCTAssertNil(link("https://demo.medpull.app/patient/"))
        XCTAssertNil(link("https://demo.medpull.app/a/"))
        XCTAssertNil(link("medpulldemo://a"))
        XCTAssertNil(link("medpulldemo://tasks/abc"))
        XCTAssertNil(link("medpulldemo://wearables"))
    }

    // MARK: The presenter's number

    func testPhoneNumbers() {
        XCTAssertEqual(PhoneNumber.normalized("(713) 555-0142"), "+17135550142")
        XCTAssertEqual(PhoneNumber.normalized("1 713 555 0142"), "+17135550142")
        XCTAssertEqual(PhoneNumber.normalized("+44 20 7946 0958"), "+442079460958")
        XCTAssertNil(PhoneNumber.normalized("555-0142"))
        XCTAssertNil(PhoneNumber.normalized(""))
        XCTAssertEqual(PhoneNumber.display("+15049081262"), "(504) 908-1262")
        XCTAssertEqual(PhoneNumber.display("+442079460958"), "+442079460958")
        XCTAssertEqual(PhoneNumber.smsURL(to: "+15049081262", body: "Hi MedPull")?.absoluteString,
                       "sms:+15049081262&body=Hi%20MedPull")
    }
}
