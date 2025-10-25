// Live Camera Simulation
const canvas = document.getElementById("camCanvas")
const ctx = canvas.getContext("2d")
const detectionOverlays = document.getElementById("detectionOverlays")

// Set canvas size
function resizeCanvas() {
  const container = canvas.parentElement
  canvas.width = container.clientWidth
  canvas.height = container.clientHeight
}

resizeCanvas()
window.addEventListener("resize", resizeCanvas)

// Detection counters
let potholeCount = 0
let puddleCount = 0
let bumpCount = 0
let adjustmentCount = 0

// Detection settings
const settings = {
  potholeDetection: true,
  puddleDetection: true,
  bumpDetection: true,
  alertsEnabled: true,
  sensitivity: 7,
  brightness: 50,
}

// Update settings from controls
document.getElementById("potholeDetection").addEventListener("change", (e) => {
  settings.potholeDetection = e.target.checked
})

document.getElementById("puddleDetection").addEventListener("change", (e) => {
  settings.puddleDetection = e.target.checked
})

document.getElementById("bumpDetection").addEventListener("change", (e) => {
  settings.bumpDetection = e.target.checked
})

document.getElementById("alertsEnabled").addEventListener("change", (e) => {
  settings.alertsEnabled = e.target.checked
})

document.getElementById("sensitivity").addEventListener("input", (e) => {
  settings.sensitivity = Number.parseInt(e.target.value)
  document.getElementById("sensitivityValue").textContent = e.target.value
})

document.getElementById("brightness").addEventListener("input", (e) => {
  settings.brightness = Number.parseInt(e.target.value)
  document.getElementById("brightnessValue").textContent = e.target.value + "%"
})

// Simulated road with obstacles
class RoadSimulator {
  constructor() {
    this.roadY = 0
    this.obstacles = []
    this.lastObstacleTime = 0
  }

  update() {
    // Move road
    this.roadY += 2
    if (this.roadY > 50) {
      this.roadY = 0
    }

    // Add random obstacles
    const now = Date.now()
    if (now - this.lastObstacleTime > 2000 + Math.random() * 3000) {
      this.addRandomObstacle()
      this.lastObstacleTime = now
    }

    // Update obstacles
    this.obstacles = this.obstacles.filter((obs) => {
      obs.y += 3
      return obs.y < canvas.height + 50
    })
  }

  addRandomObstacle() {
    const types = []
    if (settings.potholeDetection) types.push("pothole")
    if (settings.puddleDetection) types.push("puddle")
    if (settings.bumpDetection) types.push("bump")

    if (types.length === 0) return

    const type = types[Math.floor(Math.random() * types.length)]
    const x = canvas.width * 0.3 + Math.random() * canvas.width * 0.4

    this.obstacles.push({
      type,
      x,
      y: -50,
      width: 60 + Math.random() * 40,
      height: 40 + Math.random() * 30,
      detected: false,
    })
  }

  draw() {
    // Draw road
    ctx.fillStyle = "#2a2a2a"
    ctx.fillRect(0, 0, canvas.width, canvas.height)

    // Draw road lines
    ctx.strokeStyle = "#4a4a4a"
    ctx.lineWidth = 2
    ctx.setLineDash([20, 20])

    for (let i = -1; i < 10; i++) {
      const y = (i * 100 + this.roadY) % canvas.height
      ctx.beginPath()
      ctx.moveTo(canvas.width / 2, y)
      ctx.lineTo(canvas.width / 2, y + 50)
      ctx.stroke()
    }

    ctx.setLineDash([])

    // Apply brightness
    ctx.globalAlpha = settings.brightness / 100

    // Draw obstacles
    this.obstacles.forEach((obs) => {
      // Detect obstacles in detection zone
      if (obs.y > canvas.height * 0.3 && obs.y < canvas.height * 0.5 && !obs.detected) {
        this.detectObstacle(obs)
        obs.detected = true
      }

      // Draw obstacle
      if (obs.type === "pothole") {
        ctx.fillStyle = "#1a1a1a"
        ctx.beginPath()
        ctx.ellipse(obs.x, obs.y, obs.width / 2, obs.height / 2, 0, 0, Math.PI * 2)
        ctx.fill()
      } else if (obs.type === "puddle") {
        ctx.fillStyle = "rgba(6, 182, 212, 0.4)"
        ctx.beginPath()
        ctx.ellipse(obs.x, obs.y, obs.width / 2, obs.height / 2, 0, 0, Math.PI * 2)
        ctx.fill()
      } else if (obs.type === "bump") {
        ctx.fillStyle = "#3a3a3a"
        ctx.fillRect(obs.x - obs.width / 2, obs.y - obs.height / 2, obs.width, obs.height)
      }

      // Draw detection box if detected
      if (obs.detected && obs.y < canvas.height * 0.7) {
        const color = obs.type === "pothole" ? "#ef4444" : obs.type === "puddle" ? "#06b6d4" : "#f59e0b"

        ctx.strokeStyle = color
        ctx.lineWidth = 3
        ctx.strokeRect(obs.x - obs.width / 2 - 10, obs.y - obs.height / 2 - 10, obs.width + 20, obs.height + 20)

        // Draw label
        ctx.fillStyle = color
        ctx.font = "bold 14px Arial"
        ctx.fillText(obs.type.toUpperCase(), obs.x - obs.width / 2 - 10, obs.y - obs.height / 2 - 15)
      }
    })

    ctx.globalAlpha = 1

    // Draw detection zone
    ctx.strokeStyle = "rgba(59, 130, 246, 0.3)"
    ctx.lineWidth = 2
    ctx.strokeRect(canvas.width * 0.2, canvas.height * 0.3, canvas.width * 0.6, canvas.height * 0.2)

    // Draw detection zone label
    ctx.fillStyle = "rgba(59, 130, 246, 0.8)"
    ctx.font = "12px Arial"
    ctx.fillText("DETECTION ZONE", canvas.width * 0.2 + 10, canvas.height * 0.3 + 20)
  }

  detectObstacle(obs) {
    // Update counters
    if (obs.type === "pothole") {
      potholeCount++
      document.getElementById("potholeCount").textContent = potholeCount
    } else if (obs.type === "puddle") {
      puddleCount++
      document.getElementById("puddleCount").textContent = puddleCount
    } else if (obs.type === "bump") {
      bumpCount++
      document.getElementById("bumpCount").textContent = bumpCount
    }

    adjustmentCount++
    document.getElementById("adjustmentCount").textContent = adjustmentCount

    // Add to recent detections
    addDetectionToList(obs.type)

    // Show alert if enabled
    if (settings.alertsEnabled) {
      showAlert(obs.type)
    }
  }
}

function addDetectionToList(type) {
  const detectionsList = document.getElementById("detectionsList")
  const now = new Date()
  const timeString = now.toLocaleTimeString()

  const detectionItem = document.createElement("div")
  detectionItem.className = "detection-item"
  detectionItem.innerHTML = `
    <div class="detection-type">
      <span class="detection-badge ${type}">${type.toUpperCase()}</span>
      <span>Detected ahead</span>
    </div>
    <span class="detection-time">${timeString}</span>
  `

  detectionsList.insertBefore(detectionItem, detectionsList.firstChild)

  // Keep only last 10 detections
  while (detectionsList.children.length > 10) {
    detectionsList.removeChild(detectionsList.lastChild)
  }
}

function showAlert(type) {
  // Create alert notification (could be enhanced with a toast notification)
  console.log(`[v0] Alert: ${type} detected ahead!`)
}

// Initialize and animate
const roadSim = new RoadSimulator()

function animate() {
  roadSim.update()
  roadSim.draw()
  requestAnimationFrame(animate)
}

animate()

console.log("[v0] Live cam simulation started")
