document.addEventListener("DOMContentLoaded", () => {
  const form = document.querySelector("[data-application-form]");

  if (!form) {
    return;
  }

  const storageKey = "traditional-strength-coaching-application";
  const steps = Array.from(form.querySelectorAll("[data-step]"));
  const progressItems = Array.from(
    document.querySelectorAll("[data-progress-step]")
  );
  const progressBar = document.querySelector("[data-progress-bar]");
  const saveStatus = document.querySelector("[data-save-status]");
  const reviewOutput = document.querySelector("[data-review-output]");
  let currentStep = 1;
  let saveMessageTimer;

  const labels = {
    first_name: "First name",
    last_name: "Last name",
    email: "Email",
    instagram: "Instagram",
    country: "Country",
    age: "Age",
    bodyweight_kg: "Bodyweight",
    squat_kg: "Squat",
    bench_kg: "Bench",
    deadlift_kg: "Deadlift",
    years_training: "Years training",
    training_days: "Training days",
    next_competition: "Competition planned",
    primary_goal: "Working towards",
    biggest_problem: "Holding you back",
    current_program: "Biggest frustration",
    injury_history: "Injuries or recurring pain",
    previous_coaching: "Why coaching now",
    coaching_expectations: "Successful coaching looks like",
    video_feedback_ready: "Send training videos",
    communication_ready: "Communicate consistently",
    minimum_term_ready: "Follow the programme",
    referral_source: "Found Traditional Strength",
    anything_else: "Anything else",
  };

  const sections = [
    {
      title: "About you",
      fields: [
        "first_name",
        "last_name",
        "email",
        "instagram",
        "country",
        "age",
      ],
    },
    {
      title: "Your lifting",
      fields: [
        "bodyweight_kg",
        "squat_kg",
        "bench_kg",
        "deadlift_kg",
        "years_training",
        "training_days",
        "next_competition",
      ],
    },
    {
      title: "Your training",
      fields: [
        "primary_goal",
        "biggest_problem",
        "current_program",
        "injury_history",
      ],
    },
    {
      title: "Working together",
      fields: [
        "previous_coaching",
        "coaching_expectations",
        "video_feedback_ready",
        "communication_ready",
        "minimum_term_ready",
        "referral_source",
        "anything_else",
      ],
    },
  ];

  const getField = (name) => form.elements.namedItem(name);

  const getValue = (name) => {
    const field = getField(name);

    if (!field) {
      return "";
    }

    if (field.type === "checkbox") {
      return field.checked ? "Yes" : "No";
    }

    return field.value.trim();
  };

  const showSaveMessage = (message) => {
    if (!saveStatus) {
      return;
    }

    window.clearTimeout(saveMessageTimer);
    saveStatus.textContent = message;
    saveStatus.classList.add("is-visible");

    saveMessageTimer = window.setTimeout(() => {
      saveStatus.classList.remove("is-visible");
    }, 1800);
  };

  const saveProgress = ({ announce = true } = {}) => {
    const payload = {};

    Array.from(form.elements).forEach((field) => {
      if (!field.name || field.name === "website") {
        return;
      }

      payload[field.name] =
        field.type === "checkbox" ? field.checked : field.value;
    });

    payload.currentStep = currentStep;
    localStorage.setItem(storageKey, JSON.stringify(payload));

    if (announce) {
      showSaveMessage("Progress saved in this browser.");
    }
  };

  const restoreProgress = () => {
    const raw = localStorage.getItem(storageKey);

    if (!raw) {
      return false;
    }

    try {
      const saved = JSON.parse(raw);

      Object.entries(saved).forEach(([name, value]) => {
        if (name === "currentStep") {
          return;
        }

        const field = getField(name);

        if (!field) {
          return;
        }

        if (field.type === "checkbox") {
          field.checked = Boolean(value);
        } else {
          field.value = value;
        }
      });

      currentStep = Math.min(Math.max(Number(saved.currentStep) || 1, 1), 5);
      return true;
    } catch {
      localStorage.removeItem(storageKey);
      return false;
    }
  };

  const updateProgress = () => {
    const progress = ((currentStep - 1) / 4) * 100;

    if (progressBar) {
      progressBar.style.width = `${progress}%`;
    }

    progressItems.forEach((item, index) => {
      const stepNumber = index + 1;

      item.classList.toggle("is-active", stepNumber === currentStep);
      item.classList.toggle("is-complete", stepNumber < currentStep);
    });
  };

  const showStep = (stepNumber, { announceSave = false } = {}) => {
    currentStep = stepNumber;

    steps.forEach((step) => {
      const isCurrent = Number(step.dataset.step) === currentStep;
      step.hidden = !isCurrent;
      step.classList.toggle("is-active", isCurrent);
    });

    updateProgress();
    saveProgress({ announce: announceSave });

    const activeStep = steps.find(
      (step) => Number(step.dataset.step) === currentStep
    );

    activeStep?.querySelector("input, textarea, select")?.focus({
      preventScroll: true,
    });

    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const validateStep = (stepNumber) => {
    const step = steps.find(
      (item) => Number(item.dataset.step) === stepNumber
    );

    if (!step) {
      return true;
    }

    const requiredFields = Array.from(step.querySelectorAll("[required]"));
    let isValid = true;

    requiredFields.forEach((field) => {
      const valid =
        field.type === "checkbox" ? field.checked : field.value.trim();

      field.setAttribute("aria-invalid", valid ? "false" : "true");

      const error = form.querySelector(
        `[data-error-for="${field.name}"]`
      );

      if (!valid) {
        isValid = false;

        if (error && !error.textContent.trim()) {
          error.textContent = "Complete this before continuing.";
        }
      } else if (error) {
        error.textContent = "";
      }
    });

    if (!isValid) {
      step.querySelector('[aria-invalid="true"]')?.focus();
    }

    return isValid;
  };

  const renderReview = () => {
    if (!reviewOutput) {
      return;
    }

    reviewOutput.innerHTML = "";

    sections.forEach((section) => {
      const wrapper = document.createElement("section");
      wrapper.className = "review-section";

      const heading = document.createElement("h3");
      heading.textContent = section.title;
      wrapper.appendChild(heading);

      const list = document.createElement("dl");
      list.className = "review-list";

      section.fields.forEach((name) => {
        const value = getValue(name);

        if (!value) {
          return;
        }

        const row = document.createElement("div");
        const term = document.createElement("dt");
        const description = document.createElement("dd");

        term.textContent = labels[name] || name;
        description.textContent = value;

        row.append(term, description);
        list.appendChild(row);
      });

      wrapper.appendChild(list);
      reviewOutput.appendChild(wrapper);
    });
  };

  const restored = restoreProgress();

  if (restored) {
    showSaveMessage("Saved application restored.");
  }

  form.addEventListener("input", () => saveProgress());
  form.addEventListener("change", () => saveProgress());

  form.querySelectorAll("[data-next-step]").forEach((button) => {
    button.addEventListener("click", () => {
      if (!validateStep(currentStep)) {
        return;
      }

      showStep(Math.min(currentStep + 1, 4), { announceSave: true });
    });
  });

  form.querySelectorAll("[data-previous-step]").forEach((button) => {
    button.addEventListener("click", () => {
      showStep(Math.max(currentStep - 1, 1));
    });
  });

  form.querySelector("[data-review-step]")?.addEventListener("click", () => {
    if (!validateStep(4)) {
      return;
    }

    renderReview();
    showStep(5, { announceSave: true });
  });

  form.addEventListener("submit", (event) => {
    if (!validateStep(5)) {
      event.preventDefault();
      return;
    }

    localStorage.removeItem(storageKey);
  });

  if (currentStep === 5) {
    renderReview();
  }

  showStep(currentStep);
});
