# Shared Household Chores

A web application designed to solve chore confusion in shared living spaces. The core problem this project addresses is simple: **housemates don't know whose turn it is to do a specific chore.**

This platform establishes accountability, clarity, and fairness by tracking recurring household chores and automatically rotating assignments among housemates.

---

## 🚀 Core MVP Features

### 1. Household Management
- **Single Admin Model:** Each household has one designated administrator who manages the household settings and members.
- **Join via Code:** New housemates can easily join an existing household using a unique, shareable join code.
- **Member Directory:** Full visibility into current household members and their roles.
- **Member Removal:** Admin can remove housemates who move out, automatically updating chore rotations and assignments.

### 2. Chore Management
- **Admin Control:** The household admin can create, update, and delete chores.
- **Custom Frequencies & Schedules:** Chores can be scheduled with flexible recurrence patterns (daily, weekly, bi-weekly, monthly, etc.).
- **Clear Descriptions:** Chores include instructions, expectations, and recurrence rules.

### 3. Chore Assignments & Rotations
- **Automated Fair Rotation:** Chores automatically rotate between members so duties are evenly shared.
- **Upcoming Chore Dashboard:** Housemates have immediate visibility into upcoming tasks and whose turn is next.
- **One-Click Completion:** Members can mark assigned chores as complete when finished.

### 4. Notifications & History
- **Chore Reminders:** Housemates receive reminders for their upcoming chores.
- **Overdue Alerts:** The admin receives notifications when chores pass their due date without completion.
- **Completed Chore History:** A transparent, historical log of completed chores with completion dates and assignees.

---

## 📌 Business Logic & Key Behaviors

- **Admin Participation:** The admin is not just a manager; they participate in chore rotations equally alongside all housemates.
- **Automatic Onboarding into Rotations:** Whenever a new member joins via the household join code, they are automatically incorporated into existing chore rotation queues.
- **Sticky Overdue Chores:** An overdue chore remains assigned to the delinquent member until they complete it (no skipping or passing the burden to the next person).
- **Member Removal Resilience:** When a member is removed from a household, they are removed from all future rotations, and any pending/overdue assignments currently assigned to them are immediately reassigned.
- **Date-Based Scheduling:** The initial release uses calendar due dates (e.g., `YYYY-MM-DD`) rather than specific due timestamps, keeping household expectations intuitive and low-stress.

---

## 🛠 Planned Tech Stack

- **Backend:** Python / Django
- **Database:** SQLite (local development), PostgreSQL (production-ready)
- **Frontend:** Django Templates with modern Vanilla CSS & JavaScript
- **Background Tasks / Scheduling:** Django Management Commands / Scheduled Cron Jobs

---

## 📖 Documentation & Architecture

For a comprehensive breakdown of the application architecture, data models, state workflows, edge cases, and phase-by-phase implementation plan, see:
- [_docs/plan.md](_docs/plan.md)
