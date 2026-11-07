.PHONY: setup seed dev dev-backend dev-frontend dev-patient-web build build-patient-web run test lint clean \
        deploy deploy-backend reseed destroy deploy-demo deploy-demo-backend reseed-demo destroy-demo \
        audit-compartments ios ios-build openapi android-build android-test android-install

setup: ## Install backend (uv) and frontend (npm) dependencies
	cd backend && uv sync
	cd frontend && npm install

seed: ## (Re)create the database with deterministic demo data
	cd backend && uv run python -m app.seed.seed --reset

dev-backend: ## FastAPI with auto-reload on :8000
	cd backend && uv run uvicorn app.main:app --reload --port 8000

dev-frontend: ## Vite dev server on :5173 (proxies /api -> :8000)
	cd frontend && npm run dev

dev-patient-web: ## Vite dev server for the patient web app on :5174 (proxies /api -> :8000)
	cd patient-web && npm run dev

build-patient-web: ## Production build of the patient web app (patient-web/dist)
	cd patient-web && npm run build

dev: ## Run backend + frontend together
	cd frontend && npx concurrently -k -n api,web -c blue,green \
		"cd ../backend && uv run uvicorn app.main:app --reload --port 8000" \
		"npm run dev"

build: ## Production frontend build (served by FastAPI in `make run`)
	cd frontend && npm run build

run: ## Single-process demo: API + built frontend on :8000
	cd backend && uv run uvicorn app.main:app --port 8000

test: ## Backend test suite (pytest). There are no frontend tests.
	cd backend && uv run pytest -q

lint: ## ESLint over frontend and patient-web + ruff over backend/app and backend/tests
	cd frontend && npm run lint
	cd patient-web && npm run lint
	cd backend && uv run ruff check app tests

openapi: ## Refresh backend/openapi.json, the contract the patient apps are generated against
	cd backend && uv run python scripts/export_openapi.py

deploy: ## Deploy the real app to AWS, from .env (see infra/README.md)
	./infra/deploy.sh

deploy-backend: ## Deploy the real app's API only, skipping the frontend build
	./infra/deploy.sh --backend-only

reseed: ## Rebuild the database (the real stack refuses this; use reseed-demo)
	./infra/deploy.sh --reseed

destroy: ## Tear the real app's stack down
	./infra/destroy.sh

deploy-demo: ## Deploy the public demo stack, from .env.demo
	./infra/deploy.sh --env .env.demo

deploy-demo-backend: ## Demo stack, API only
	./infra/deploy.sh --env .env.demo --backend-only

reseed-demo: ## Rebuild the demo stack's database (dates shift to today)
	./infra/deploy.sh --env .env.demo --reseed

destroy-demo: ## Tear the demo stack down
	./infra/destroy.sh --env .env.demo

# The local database by default; AUDIT="--stack recovery-copilot" reads the
# deployed one (read-only, no lock) and what AWS says about its compartments.
AUDIT ?= --local data/recovery.db

audit-compartments: ## Who is in each compartment (hospitals, sports orgs, subscribers, console credentials) and, with AUDIT="--stack NAME", the buckets, keys, trail and tags
	cd backend && uv run python scripts/audit_compartments.py $(AUDIT)

ios: ## Generate the Xcode project for the patient app (needs xcodegen) and open it
	cd ios && xcodegen generate && open MedPull.xcodeproj

ios-build: ## Build the patient app for the iPhone simulator (CI-style, no signing)
	cd ios && xcodegen generate && xcodebuild -project MedPull.xcodeproj -scheme MedPull \
		-destination 'platform=iOS Simulator,name=iPhone 17' CODE_SIGNING_ALLOWED=NO build

# Android Studio's JDK unless JAVA_HOME is already set (CI sets it).
ANDROID_JAVA_HOME ?= $(or $(JAVA_HOME),/c/Program Files/Android/Android Studio/jbr)

android-build: ## Debug APK of the Android patient app
	cd android && JAVA_HOME="$(ANDROID_JAVA_HOME)" ./gradlew :app:assembleDebug -q

android-test: ## Unit tests and Android lint for the patient app
	cd android && JAVA_HOME="$(ANDROID_JAVA_HOME)" ./gradlew :app:testDebugUnitTest :app:lintDebug -q

android-install: ## Install the debug APK on the connected device or emulator
	"$(LOCALAPPDATA)/Android/Sdk/platform-tools/adb" install -r android/app/build/outputs/apk/debug/app-debug.apk

clean: ## Remove the local database, the frontend build, and the Lambda build dir
	rm -rf backend/data/*.db frontend/dist infra/.build
