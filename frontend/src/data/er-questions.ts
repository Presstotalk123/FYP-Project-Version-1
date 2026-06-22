import { QuestionCardData } from "@/components/QuestionCard";

export const erQuestions: QuestionCardData[] = [
  {
    id: 1,
    title: "University Enrollment",
    summary: "Model students, courses, and enrollments.",
    description:
      "Design an ER diagram for a university course enrollment system. Include students, courses, instructors, sections, and enrollment records with appropriate keys and cardinalities.",
    difficulty: "Easy",
  },
  {
    id: 2,
    title: "Online Bookstore",
    summary: "Orders, reviews, and shipping workflows.",
    description:
      "Create an ER diagram for an online bookstore that supports customers, books, authors, orders, order items, reviews, and shipments. Capture key constraints and relationships.",
    difficulty: "Medium",
  },
  {
    id: 3,
    title: "SaaS Billing",
    summary: "Tenants, plans, usage, and invoices.",
    description:
      "Model a multi-tenant SaaS billing platform with tenants, users, plans, subscriptions, usage tracking, invoices, and payments. Show how tenant isolation is enforced.",
    difficulty: "Hard",
  },
  {
    id: 4,
    title: "Hospital Records",
    summary: "Appointments, patients, and medical records.",
    description:
      "Design an ER diagram for a hospital system including patients, doctors, appointments, departments, and medical records. Include constraints for scheduling.",
    difficulty: "Medium",
  },
  {
    id: 5,
    title: "Ride Sharing",
    summary: "Trips, drivers, riders, and pricing.",
    description:
      "Create an ER diagram for a ride-sharing service with riders, drivers, vehicles, trips, pricing rules, and payments. Represent surge pricing logic.",
    difficulty: "Hard",
  },
  {
    id: 6,
    title: "Library Management",
    summary: "Books, members, and loans.",
    description:
      "Design an ER diagram for a library system including books, copies, members, loans, reservations, and fines. Show borrowing limits and overdue handling.",
    difficulty: "Easy",
  },
];
