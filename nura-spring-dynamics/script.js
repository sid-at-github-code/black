// Theme Toggle
const themeToggle = document.getElementById("themeToggle")
const body = document.body

// Check for saved theme preference or default to dark mode
const currentTheme = localStorage.getItem("theme") || "dark"
if (currentTheme === "light") {
  body.classList.add("light-mode")
}

themeToggle.addEventListener("click", () => {
  body.classList.toggle("light-mode")

  // Save theme preference
  const theme = body.classList.contains("light-mode") ? "light" : "dark"
  localStorage.setItem("theme", theme)

  // Add animation effect
  themeToggle.style.transform = "rotate(360deg)"
  setTimeout(() => {
    themeToggle.style.transform = "rotate(0deg)"
  }, 300)
})

// Mobile Menu Toggle
const mobileMenuToggle = document.getElementById("mobileMenuToggle")
const navLinks = document.querySelector(".nav-links")

if (mobileMenuToggle) {
  mobileMenuToggle.addEventListener("click", () => {
    navLinks.classList.toggle("active")
    mobileMenuToggle.classList.toggle("active")
  })
}

// Smooth scroll for anchor links
document.querySelectorAll('a[href^="#"]').forEach((anchor) => {
  anchor.addEventListener("click", function (e) {
    e.preventDefault()
    const target = document.querySelector(this.getAttribute("href"))
    if (target) {
      target.scrollIntoView({
        behavior: "smooth",
        block: "start",
      })
    }
  })
})

// Animated counter for stats
function animateCounter(element, target, duration = 2000) {
  const start = 0
  const increment = target / (duration / 16)
  let current = start

  const timer = setInterval(() => {
    current += increment
    if (current >= target) {
      element.textContent = Math.round(target)
      clearInterval(timer)
    } else {
      element.textContent = Math.round(current)
    }
  }, 16)
}

// Intersection Observer for animations
const observerOptions = {
  threshold: 0.1,
  rootMargin: "0px 0px -50px 0px",
}

const observer = new IntersectionObserver((entries) => {
  entries.forEach((entry) => {
    if (entry.isIntersecting) {
      entry.target.style.opacity = "1"
      entry.target.style.transform = "translateY(0)"

      // Animate stats if they exist
      if (entry.target.classList.contains("stat-item")) {
        const numberElement = entry.target.querySelector(".stat-number")
        const target = Number.parseFloat(numberElement.getAttribute("data-target"))
        animateCounter(numberElement, target)
      }

      observer.unobserve(entry.target)
    }
  })
}, observerOptions)

// Observe elements for animation
document.addEventListener("DOMContentLoaded", () => {
  // Animate feature cards
  document.querySelectorAll(".feature-card").forEach((card, index) => {
    card.style.opacity = "0"
    card.style.transform = "translateY(30px)"
    card.style.transition = `all 0.6s ease ${index * 0.1}s`
    observer.observe(card)
  })

  // Animate value cards
  document.querySelectorAll(".value-card").forEach((card, index) => {
    card.style.opacity = "0"
    card.style.transform = "translateY(30px)"
    card.style.transition = `all 0.6s ease ${index * 0.1}s`
    observer.observe(card)
  })

  // Animate timeline items
  document.querySelectorAll(".timeline-item").forEach((item, index) => {
    item.style.opacity = "0"
    item.style.transform = "translateX(-30px)"
    item.style.transition = `all 0.6s ease ${index * 0.15}s`
    observer.observe(item)
  })

  // Animate team members
  document.querySelectorAll(".team-member").forEach((member, index) => {
    member.style.opacity = "0"
    member.style.transform = "translateY(30px)"
    member.style.transition = `all 0.6s ease ${index * 0.1}s`
    observer.observe(member)
  })

  // Animate stat items
  document.querySelectorAll(".stat-item").forEach((stat, index) => {
    stat.style.opacity = "0"
    stat.style.transform = "translateY(30px)"
    stat.style.transition = `all 0.6s ease ${index * 0.1}s`
    observer.observe(stat)
  })
})

// Navbar scroll effect
let lastScroll = 0
const navbar = document.querySelector(".navbar")

window.addEventListener("scroll", () => {
  const currentScroll = window.pageYOffset

  if (currentScroll > 100) {
    navbar.style.padding = "12px 0"
    navbar.style.boxShadow = "0 4px 12px rgba(0, 0, 0, 0.1)"
  } else {
    navbar.style.padding = "16px 0"
    navbar.style.boxShadow = "none"
  }

  lastScroll = currentScroll
})

// Contact form handling
const contactForm = document.getElementById("contactForm")
if (contactForm) {
  contactForm.addEventListener("submit", (e) => {
    e.preventDefault()

    // Simulate form submission
    const formData = new FormData(contactForm)
    console.log("[v0] Form submitted with data:", Object.fromEntries(formData))

    // Show success message
    contactForm.style.display = "none"
    document.getElementById("formSuccess").classList.add("show")

    // Reset form after 3 seconds
    setTimeout(() => {
      contactForm.reset()
      contactForm.style.display = "block"
      document.getElementById("formSuccess").classList.remove("show")
    }, 5000)
  })
}

// Add parallax effect to hero background
const hero = document.querySelector(".hero")
if (hero) {
  window.addEventListener("scroll", () => {
    const scrolled = window.pageYOffset
    const heroBackground = hero.querySelector(".hero-background")
    if (heroBackground) {
      heroBackground.style.transform = `translateY(${scrolled * 0.5}px)`
    }
  })
}

// Add hover effect to buttons
document.querySelectorAll(".btn").forEach((btn) => {
  btn.addEventListener("mouseenter", function () {
    this.style.transition = "all 0.3s ease"
  })
})

console.log("[v0] Script loaded successfully")
