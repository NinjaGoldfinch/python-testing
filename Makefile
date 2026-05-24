PYTHON := python3

.PHONY: run verify check

run:
	cd rest_api_examples && $(PYTHON) main.py

verify:
	$(PYTHON) rest_api_examples/02-pydantic-schemas/pydantic_example.py
	$(PYTHON) rest_api_examples/03-service-methods/service_example.py
	$(PYTHON) rest_api_examples/04-database-models-repositories/database_example.py
	$(PYTHON) rest_api_examples/05-dependency-injection/dependency_injection_example.py
	$(PYTHON) rest_api_examples/06-error-handling/error_handling_example.py
	$(PYTHON) rest_api_examples/07-auth-permissions/auth_permissions_example.py
	$(PYTHON) rest_api_examples/08-tests/tests_example.py
	$(PYTHON) rest_api_examples/09-observability-deployment/observability_deployment_example.py

check:
	$(PYTHON) -m py_compile rest_api_examples/main.py
	$(PYTHON) -m py_compile rest_api_examples/01-fastapi-app-routers/fastapi_example.py
	$(PYTHON) -m py_compile rest_api_examples/02-pydantic-schemas/pydantic_example.py
	$(PYTHON) -m py_compile rest_api_examples/03-service-methods/service_example.py
	$(PYTHON) -m py_compile rest_api_examples/04-database-models-repositories/database_example.py
	$(PYTHON) -m py_compile rest_api_examples/05-dependency-injection/dependency_injection_example.py
	$(PYTHON) -m py_compile rest_api_examples/06-error-handling/error_handling_example.py
	$(PYTHON) -m py_compile rest_api_examples/07-auth-permissions/auth_permissions_example.py
	$(PYTHON) -m py_compile rest_api_examples/08-tests/tests_example.py
	$(PYTHON) -m py_compile rest_api_examples/09-observability-deployment/observability_deployment_example.py
