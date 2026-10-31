(function () {
  const input = document.querySelector(".search");
  const blocks = Array.from(document.querySelectorAll(".block"));
  const empty = document.querySelector(".empty");
  const links = Array.from(document.querySelectorAll(".cats a"));

  function applyFilter() {
    const q = (input.value || "").trim().toLowerCase();
    let any = false;
    blocks.forEach((block) => {
      let visible = 0;
      block.querySelectorAll("[data-q]").forEach((item) => {
        const show = !q || item.dataset.q.includes(q);
        item.hidden = !show;
        if (show) visible += 1;
      });
      block.querySelectorAll(".group").forEach((group) => {
        const shown = Array.from(group.querySelectorAll("[data-q]")).some((item) => !item.hidden);
        group.hidden = !shown;
      });
      block.hidden = visible === 0;
      if (visible) any = true;
    });
    if (empty) empty.hidden = any || !q;
  }

  if (input) {
    input.addEventListener("input", applyFilter);
  }

  function setActive(id) {
    links.forEach((link) => {
      link.classList.toggle("is-active", link.getAttribute("href") === "#" + id);
    });
  }

  links.forEach((link) => {
    link.addEventListener("click", (event) => {
      const id = link.getAttribute("href").slice(1);
      const target = document.getElementById(id);
      if (!target) return;
      event.preventDefault();
      if (input && input.value) {
        input.value = "";
        applyFilter();
      }
      setActive(id);
      target.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  });

  if (links.length && "IntersectionObserver" in window) {
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
        if (visible) setActive(visible.target.id);
      },
      { rootMargin: "-20% 0px -65% 0px", threshold: [0, 0.15, 0.4] }
    );
    blocks.forEach((block) => observer.observe(block));
  } else if (links[0]) {
    links[0].classList.add("is-active");
  }
})();
