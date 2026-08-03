'use client';

import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { DashboardLayout } from '@/components/common/DashboardLayout';
import { CourseChatBubble } from '@/components/course/CourseChatBubble';
import { UserRole } from '@/types/user.types';

const COURSE_TITLE = 'SC2207 / CZ2007 — Introduction to Databases';

const PREREQUISITES =
  'CE2101 / CZ2101 / SC2001 Algorithm Design & Analysis OR MH1403 Algorithms and Computing.';

const COURSE_AIMS =
  'Database management systems (DBMS) are software systems that control the creation, ' +
  'maintenance, and use of databases, i.e., organized collections of data. Relational DBMS ' +
  '(RDBMS) are incredibly ubiquitous today — they underlie technology used by most people ' +
  'every day if not every hour. RDBMS reside behind a huge fraction of websites; they are a ' +
  'crucial component of telecommunications systems, banking systems, video games, and just ' +
  'about any other software system or electronic device that maintains some amount of ' +
  'persistent information. As a consequence, it is important that we equip you with knowledge ' +
  'of the design of relational databases and the use of RDBMS for applications. This ' +
  'introductory course serves that purpose.';

interface ContentTopic {
  title: string;
  points: string[];
}

const LEARNING_OBJECTIVES: string[] = [
  'Explain the importance of, and uses for, databases within organizations.',
  'Design a basic relational database management system (DBMS) for storing and analyzing datasets of medium complexity.',
  'Formulate basic relational database queries and execute these in order to search and analyse underlying data.',
  'Ensure data integrity through enacting the process of database normalization.',
  'Describe the usage of indexing to improve query efficiency.',
  "Explain the significance of XML and JSON in today's world.",
];

const COURSE_CONTENT: ContentTopic[] = [
  {
    title: 'Introduction to Databases',
    points: [
      'Importance of data management',
      'Overview of DBMS',
      'DBMS Architecture',
      'Relational DBMS',
      'Physical and logical data independence',
      'Languages for databases',
      'XML',
    ],
  },
  {
    title: 'Entity-Relationship Data Model',
    points: [
      'Elements of E/R Model',
      'Design Principles',
      'Modelling of Constraints',
      'Weak Entity Sets',
    ],
  },
  {
    title: 'Relational Data Model',
    points: [
      'Basics of Relational Model',
      'E/R Diagram to Relational Design',
    ],
  },
  {
    title: 'Functional Dependencies (FD) and Normalization',
    points: [
      'Definition of Functional Dependency',
      'Keys and Superkeys',
      'Rules about FDs',
      'Closure of FDs',
      'Projecting FDs',
      'Normal Forms',
    ],
  },
  {
    title: 'Relational Algebra',
    points: [
      'Algebra of Relational Operations',
      'Relational Operations on Bags',
      'Extended Operators',
    ],
  },
  {
    title: 'Querying Relational Databases',
    points: [
      'Introduction to SQL',
      'Simple queries in SQL',
      '3-value logic',
      'Multi-Relation Queries',
      'Subqueries',
      'Full-Relation Operations',
      'Database Modifications',
      'Database definition',
      'Views',
      'Constraints and Triggers',
      'SQL in programming environment',
    ],
  },
  {
    title: 'Indexes',
    points: [
      'Motivation for indexes',
      'Declaring indexes in SQL',
      'Selection of Indexes',
    ],
  },
];

// Plain-text syllabus handed to the course assistant so it answers strictly
// from what this page shows. Built from the same constants the page renders.
const COURSE_CONTEXT = [
  `Course: ${COURSE_TITLE}`,
  '',
  `Pre-requisites: ${PREREQUISITES}`,
  '',
  `Course Aims: ${COURSE_AIMS}`,
  '',
  'Intended Learning Objectives (ILO):',
  ...LEARNING_OBJECTIVES.map((ilo) => `- ${ilo}`),
  '',
  'Course Content:',
  ...COURSE_CONTENT.map(
    (topic) => `${topic.title}\n${topic.points.map((p) => `  - ${p}`).join('\n')}`
  ),
].join('\n');

export default function StudentCoursePage() {
  return (
    <ProtectedRoute requiredRole={UserRole.STUDENT}>
      <DashboardLayout>
        {/* Header */}
        <div className="page-head">
          <div>
            <h2>SC2207 / CZ2007 — Introduction to Databases</h2>
            <p>Course information and syllabus overview.</p>
          </div>
          <div className="button-row">
            <span className="badge brand-badge">SC2207 / CZ2007</span>
          </div>
        </div>

        {/* Prerequisites */}
        <section className="card" style={{ marginBottom: 20 }}>
          <h3>Pre-requisites</h3>
          <p>
            CE2101 / CZ2101 / SC2001 Algorithm Design &amp; Analysis
            {' '}<strong>OR</strong>{' '}
            MH1403 Algorithms and Computing.
          </p>
        </section>

        {/* Course Aims */}
        <section className="card" style={{ marginBottom: 20 }}>
          <h3>Course Aims</h3>
          <p style={{ marginBottom: 12 }}>
            Database management systems (DBMS) are software systems that control the creation,
            maintenance, and use of databases, i.e., organized collections of data. Relational
            DBMS (RDBMS) are incredibly ubiquitous today — they underlie technology used by most
            people every day if not every hour.
          </p>
          <p>
            RDBMS reside behind a huge fraction of websites; they are a crucial component of
            telecommunications systems, banking systems, video games, and just about any other
            software system or electronic device that maintains some amount of persistent
            information. As a consequence, it is important that we equip you with knowledge of the
            design of relational databases and the use of RDBMS for applications. This introductory
            course serves that purpose.
          </p>
        </section>

        {/* Intended Learning Objectives */}
        <section className="card" style={{ marginBottom: 20 }}>
          <h3>Intended Learning Objectives (ILO)</h3>
          <ul style={{ margin: '4px 0 0', paddingLeft: 20, lineHeight: 1.7, color: 'var(--brand-charcoal)' }}>
            {LEARNING_OBJECTIVES.map((ilo) => (
              <li key={ilo}>{ilo}</li>
            ))}
          </ul>
        </section>

        {/* Course Content */}
        <div className="page-head" style={{ marginTop: 28, marginBottom: 16 }}>
          <div>
            <h2 style={{ fontSize: 22 }}>Course Content</h2>
          </div>
        </div>
        <div className="grid-2">
          {COURSE_CONTENT.map((topic) => (
            <article key={topic.title} className="card">
              <h3 style={{ fontSize: 16 }}>{topic.title}</h3>
              <ul style={{ margin: '4px 0 0', paddingLeft: 20, lineHeight: 1.7, color: 'var(--brand-charcoal)' }}>
                {topic.points.map((point) => (
                  <li key={point}>{point}</li>
                ))}
              </ul>
            </article>
          ))}
        </div>

        {/* Floating course assistant */}
        <CourseChatBubble courseContext={COURSE_CONTEXT} />
      </DashboardLayout>
    </ProtectedRoute>
  );
}
