"""AWS runtime adapters.

Nothing in this package is imported on the hot path of a local run: every
module degrades to a no-op when the AWS environment variables are unset, so
`make dev` behaves exactly as it did before the app learned to run on Lambda.
"""
