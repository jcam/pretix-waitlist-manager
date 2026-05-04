(function () {
    function managedFields(form) {
        return Array.from(form.querySelectorAll("select, input, textarea")).filter((field) => {
            return !["button", "submit", "hidden"].includes(field.type);
        });
    }

    function dirtyWarningFields(form) {
        return Array.from(form.querySelectorAll("select, input, textarea")).filter((field) => {
            return !["button", "submit"].includes(field.type);
        });
    }

    function storageKey(form) {
        return `pretix-waitlist-manager:${window.location.pathname}:${form.id}`;
    }

    function saveFormState(form) {
        const payload = {};
        managedFields(form).forEach((field) => {
            if (!field.name) {
                return;
            }

            if (field.type === "checkbox") {
                payload[field.name] = field.checked;
            } else if (field.type === "radio") {
                if (field.checked) {
                    payload[field.name] = field.value;
                }
            } else {
                payload[field.name] = field.value;
            }
        });
        form._waitlistManagerState = payload;
        window.sessionStorage.setItem(storageKey(form), JSON.stringify(payload));
    }

    function restoreFormState(form) {
        const payload = loadStoredState(form);
        if (!payload) {
            return;
        }

        managedFields(form).forEach((field) => {
            if (!field.name || !(field.name in payload)) {
                return;
            }

            if (field.type === "checkbox") {
                field.checked = Boolean(payload[field.name]);
            } else if (field.type === "radio") {
                field.checked = field.value === payload[field.name];
            } else {
                field.value = payload[field.name];
            }
        });
    }

    function loadStoredState(form) {
        if (form._waitlistManagerState) {
            return form._waitlistManagerState;
        }
        const raw = window.sessionStorage.getItem(storageKey(form));
        if (!raw) {
            return null;
        }

        try {
            form._waitlistManagerState = JSON.parse(raw);
            return form._waitlistManagerState;
        } catch (error) {
            window.sessionStorage.removeItem(storageKey(form));
            return null;
        }
    }

    function preferredStoredValue(form, field) {
        const payload = loadStoredState(form);
        if (!payload || !field.name || !(field.name in payload)) {
            return field.value;
        }
        return payload[field.name];
    }

    function suppressDirtyWarning(form) {
        dirtyWarningFields(form).forEach((field) => {
            field.setAttribute("data-ays-ignore", "1");
        });

        if (window.jQuery) {
            window.jQuery(form).trigger("reinitialize.areYouSure");
        }
    }

    function initializeSessionState(form) {
        loadStoredState(form);
        restoreFormState(form);

        const persist = () => saveFormState(form);
        managedFields(form).forEach((field) => {
            field.addEventListener("change", persist);
            field.addEventListener("input", persist);
        });
        form.addEventListener("submit", persist);

        suppressDirtyWarning(form);
    }

    function setSelectChoices(field, choices, currentValue) {
        field.innerHTML = "";
        choices.forEach(([value, label]) => {
            const option = document.createElement("option");
            option.value = value;
            option.textContent = label;
            if (value === currentValue) {
                option.selected = true;
            }
            field.appendChild(option);
        });

        if (!field.value && choices.length) {
            field.value = choices[0][0];
        }
    }

    function fetchJson(url, params) {
        const search = new URLSearchParams(params);
        return fetch(`${url}?${search.toString()}`, {
            headers: {
                "X-Requested-With": "XMLHttpRequest"
            }
        }).then((response) => response.json());
    }

    function initializeDependentImportSelects(preview) {
        const formId = preview.dataset.formId;
        const optionsUrl = preview.dataset.optionsUrl;
        const membershipFieldId = preview.dataset.membershipFieldId;
        const questionFieldId = preview.dataset.questionFieldId;
        const answerFieldId = preview.dataset.answerFieldId;
        if (!formId || !optionsUrl || !membershipFieldId || !questionFieldId || !answerFieldId) {
            return Promise.resolve();
        }

        const form = document.getElementById(formId);
        const membershipField = document.getElementById(membershipFieldId);
        const questionField = document.getElementById(questionFieldId);
        const answerField = document.getElementById(answerFieldId);
        if (!form || !membershipField || !questionField || !answerField) {
            return Promise.resolve();
        }

        const loadOptions = () => {
            return fetchJson(optionsUrl, {
                membership_type: membershipField.value
            }).then((payload) => {
                const questionChoices = payload.question_choices || [];
                const answerChoicesByQuestion = payload.answer_choices_by_question || {};
                const currentQuestion = preferredStoredValue(form, questionField);
                const currentAnswer = preferredStoredValue(form, answerField);

                setSelectChoices(questionField, questionChoices, currentQuestion);
                setSelectChoices(
                    answerField,
                    answerChoicesByQuestion[questionField.value] || [],
                    currentAnswer
                );
                saveFormState(form);
            });
        };

        questionField.addEventListener("change", (event) => {
            event.stopImmediatePropagation();
            loadOptions().then(() => {
                answerField.dispatchEvent(new Event("change", {bubbles: true}));
            });
        });

        membershipField.addEventListener("change", (event) => {
            event.stopImmediatePropagation();
            loadOptions().then(() => {
                answerField.dispatchEvent(new Event("change", {bubbles: true}));
            });
        });

        return loadOptions().catch(() => {
            questionField.innerHTML = "";
            answerField.innerHTML = "";
            saveFormState(form);
        });
    }

    function initializeDependentRandomizeSelects(preview) {
        const formId = preview.dataset.formId;
        const optionsUrl = preview.dataset.optionsUrl;
        const targetFieldId = preview.dataset.targetFieldId;
        const subeventFieldId = preview.dataset.subeventFieldId;
        const groupQuestionFieldId = preview.dataset.groupQuestionFieldId;
        if (!formId || !optionsUrl || !targetFieldId || !subeventFieldId || !groupQuestionFieldId) {
            return Promise.resolve();
        }

        const form = document.getElementById(formId);
        const targetField = document.getElementById(targetFieldId);
        const subeventField = document.getElementById(subeventFieldId);
        const groupQuestionField = document.getElementById(groupQuestionFieldId);
        if (!form || !targetField || !subeventField || !groupQuestionField) {
            return Promise.resolve();
        }

        const loadOptions = () => {
            return fetchJson(optionsUrl, {
                target: targetField.value,
                subevent: subeventField.value || ""
            }).then((payload) => {
                const choices = payload.group_question_choices || [["", "No group question"]];
                const currentValue = preferredStoredValue(form, groupQuestionField);
                setSelectChoices(groupQuestionField, choices, currentValue);
                saveFormState(form);
            });
        };

        const updateGroupQuestionChoices = (event) => {
            event.stopImmediatePropagation();
            loadOptions().then(() => {
                groupQuestionField.dispatchEvent(new Event("change", {bubbles: true}));
            });
        };

        targetField.addEventListener("change", updateGroupQuestionChoices);
        subeventField.addEventListener("change", updateGroupQuestionChoices);

        return loadOptions().catch(() => {
            setSelectChoices(groupQuestionField, [["", "No group question"]], "");
            saveFormState(form);
        });
    }

    function initializePreview(preview) {
        const formId = preview.dataset.formId;
        const previewUrl = preview.dataset.previewUrl;
        const errorMessage = preview.dataset.previewErrorMessage || "Preview could not be loaded.";
        const seedFieldId = preview.dataset.seedFieldId;
        const form = document.getElementById(formId);
        const extraParams = {};
        if (!form || !previewUrl) {
            return;
        }

        let timer = null;

        const loadPreview = () => {
            const data = new FormData(form);
            data.delete("csrfmiddlewaretoken");
            const params = new URLSearchParams();
            for (const [key, value] of data.entries()) {
                params.append(key, value);
            }
            Object.entries(extraParams).forEach(([key, value]) => {
                params.set(key, value);
            });

            fetch(`${previewUrl}?${params.toString()}`, {
                headers: {
                    "X-Requested-With": "XMLHttpRequest"
                }
            })
                .then((response) => response.json())
                .then((payload) => {
                    preview.innerHTML = payload.html;
                    if (seedFieldId && payload.seed) {
                        const seedField = document.getElementById(seedFieldId);
                        if (seedField) {
                            seedField.value = payload.seed;
                        }
                    }
                })
                .catch(() => {
                    preview.innerHTML = `<div class="alert alert-warning">${errorMessage}</div>`;
                });
        };

        const schedulePreview = () => {
            if (timer) {
                window.clearTimeout(timer);
            }
            timer = window.setTimeout(loadPreview, 150);
        };

        const resetPagingAndSchedulePreview = () => {
            Object.keys(extraParams).forEach((key) => {
                delete extraParams[key];
            });
            schedulePreview();
        };

        form.querySelectorAll("select, input").forEach((field) => {
            if (field.type === "submit") {
                return;
            }
            field.addEventListener("change", resetPagingAndSchedulePreview);
        });

        preview.addEventListener("click", (event) => {
            const trigger = event.target.closest("[data-preview-page-key]");
            if (!trigger) {
                return;
            }
            event.preventDefault();
            extraParams[trigger.dataset.previewPageKey] = trigger.dataset.previewPageValue;
            loadPreview();
        });

        loadPreview();
    }

    function initialize() {
        document.querySelectorAll("#waitlist-import-form, #waitlist-randomize-form").forEach((form) => {
            initializeSessionState(form);
        });

        document.querySelectorAll(".waitlist-manager-preview").forEach((preview) => {
            Promise.all([
                initializeDependentImportSelects(preview),
                initializeDependentRandomizeSelects(preview)
            ]).finally(() => {
                initializePreview(preview);
            });
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initialize);
    } else {
        initialize();
    }
}());
