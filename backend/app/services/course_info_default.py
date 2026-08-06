"""Code default for the course syllabus.

Rendered as Markdown and served by GET /course-info whenever no CourseInfo row
exists yet (before staff make their first edit). Ported verbatim from the content
that previously lived hardcoded in frontend/src/app/student/course/page.tsx, so
the student page looks the same on day one.
"""

DEFAULT_COURSE_INFO_MD = """\
# SC2207 / CZ2007 — Introduction to Databases

## Pre-requisites

CE2101 / CZ2101 / SC2001 Algorithm Design & Analysis **OR** MH1403 Algorithms and Computing.

## Course Aims

Database management systems (DBMS) are software systems that control the creation,
maintenance, and use of databases, i.e., organized collections of data. Relational DBMS
(RDBMS) are incredibly ubiquitous today — they underlie technology used by most people
every day if not every hour. RDBMS reside behind a huge fraction of websites; they are a
crucial component of telecommunications systems, banking systems, video games, and just
about any other software system or electronic device that maintains some amount of
persistent information. As a consequence, it is important that we equip you with knowledge
of the design of relational databases and the use of RDBMS for applications. This
introductory course serves that purpose.

## Intended Learning Objectives (ILO)

- Explain the importance of, and uses for, databases within organizations.
- Design a basic relational database management system (DBMS) for storing and analyzing datasets of medium complexity.
- Formulate basic relational database queries and execute these in order to search and analyse underlying data.
- Ensure data integrity through enacting the process of database normalization.
- Describe the usage of indexing to improve query efficiency.
- Explain the significance of XML and JSON in today's world.

## Course Content

### Introduction to Databases

- Importance of data management
- Overview of DBMS
- DBMS Architecture
- Relational DBMS
- Physical and logical data independence
- Languages for databases
- XML

### Entity-Relationship Data Model

- Elements of E/R Model
- Design Principles
- Modelling of Constraints
- Weak Entity Sets

### Relational Data Model

- Basics of Relational Model
- E/R Diagram to Relational Design

### Functional Dependencies (FD) and Normalization

- Definition of Functional Dependency
- Keys and Superkeys
- Rules about FDs
- Closure of FDs
- Projecting FDs
- Normal Forms

### Relational Algebra

- Algebra of Relational Operations
- Relational Operations on Bags
- Extended Operators

### Querying Relational Databases

- Introduction to SQL
- Simple queries in SQL
- 3-value logic
- Multi-Relation Queries
- Subqueries
- Full-Relation Operations
- Database Modifications
- Database definition
- Views
- Constraints and Triggers
- SQL in programming environment

### Indexes

- Motivation for indexes
- Declaring indexes in SQL
- Selection of Indexes
"""
