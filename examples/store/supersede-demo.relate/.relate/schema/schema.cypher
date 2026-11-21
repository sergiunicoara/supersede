CREATE FULLTEXT INDEX `topic_text` FOR (n:`Topic`) ON EACH [n.`description`] OPTIONS {indexConfig: {`fulltext.analyzer`: 'standard-no-stop-words',`fulltext.eventually_consistent`: false}};
