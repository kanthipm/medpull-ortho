"""Between visits: what a physical-therapy clinic keeps about a person on its
own program beyond the exercise calendar (app/hep).

The calendar says what was set and what was done. This package holds the
rest of what the clinic follows a lifter by: where it hurt at the
evaluation and where it hurts now, how the morning after a loaded session
went, the things the person wants to get back to and how they rate them,
the Friday word on the week, the phases of a protocol and the criteria the
therapist ticks to move on, the numbers from a test day, the page a trainer
reads, the scores of outcome measures, the visits themselves, and the
clinic's own settings: what each flag fires on, the fixed words for a short
list of worrying answers, and which questions cannot wait for the weekly
block.

Three rules hold across all of it:

* Nothing here authors a dose or moves a phase. The therapist clicks; the
  software records.
* Nothing here is written by a model. A reply the clinic did not write is
  not sent.
* Everything the patient is asked travels as a task (app/tasks), so the
  phone, the browser app and a text all ask it the same way.

``docs/dev/pt.md`` is the contract.
"""
