-- Sample data for CampusConnect: venues, clubs, users, students, events, registrations, expenses.
-- Before running: replace PASTE_HASH_HERE with a scrypt hash. Make one with:
--   python -c "from werkzeug.security import generate_password_hash; print(generate_password_hash('YourPassword123', method='scrypt'))"
-- Run once on a migrated database (flask --app app db upgrade first).
-- Running twice fails safely: UNIQUE rules reject duplicates and the transaction rolls back.
-- All sample users share the password used to make the hash.
BEGIN;

-- 1. Venues
INSERT INTO venues (venue_name, location, capacity) VALUES
('ECE Seminar Room', 'ECE Building, Floor 3', 80),
('University Auditorium', 'Administrative Building', 500),
('Central Field', 'Campus Center', 1000),
('Computer Lab 2', 'CSE Building, Floor 2', 50);

-- 2. Clubs
INSERT INTO clubs (club_name, description) VALUES
('Robotics Club', 'Builds robots and runs electronics workshops.'),
('Cultural Society', 'Organizes music, poetry, and cultural nights.'),
('Sports Club', 'Runs inter-department tournaments and fitness events.'),
('Entrepreneurship Club', 'Startup talks, pitch days, and business workshops.');

-- 3. Users (2 club admins + 8 students), all with the same password
INSERT INTO users (full_name, email, password_hash, role)
SELECT v.full_name, v.email, 'PASTE_HASH_HERE', v.role
FROM (VALUES
 ('Kamal Hossain', 'kamal.admin@example.edu', 'club_admin'),
 ('Lima Begum', 'lima.admin@example.edu', 'club_admin'),
 ('Rafi Ahmed', 'rafi.ahmed@example.edu', 'student'),
 ('Tasnim Akter', 'tasnim.akter@example.edu', 'student'),
 ('Sabbir Hossain', 'sabbir.hossain@example.edu', 'student'),
 ('Mahin Islam', 'mahin.islam@example.edu', 'student'),
 ('Nabila Khan', 'nabila.khan@example.edu', 'student'),
 ('Imran Hossain', 'imran.hossain@example.edu', 'student'),
 ('Sadia Rahman', 'sadia.rahman@example.edu', 'student'),
 ('Arif Chowdhury', 'arif.chowdhury@example.edu', 'student')
) AS v(full_name, email, role);

-- 4. Student profiles
INSERT INTO students (user_id, student_number, department, batch)
SELECT u.user_id, v.student_number, v.department, v.batch
FROM (VALUES
 ('rafi.ahmed@example.edu', 'S-2021-001', 'ECE', '2021'),
 ('tasnim.akter@example.edu', 'S-2021-002', 'CSE', '2021'),
 ('sabbir.hossain@example.edu', 'S-2021-003', 'EEE', '2021'),
 ('mahin.islam@example.edu', 'S-2021-004', 'ECE', '2021'),
 ('nabila.khan@example.edu', 'S-2022-001', 'CSE', '2022'),
 ('imran.hossain@example.edu', 'S-2022-002', 'ME', '2022'),
 ('sadia.rahman@example.edu', 'S-2022-003', 'ECE', '2022'),
 ('arif.chowdhury@example.edu', 'S-2022-004', 'CE', '2022')
) AS v(email, student_number, department, batch)
JOIN users u ON u.email = v.email;

-- 5. Club admin assignments
INSERT INTO club_admins (club_id, user_id)
SELECT c.club_id, u.user_id
FROM (VALUES
 ('Robotics Club', 'kamal.admin@example.edu'),
 ('Entrepreneurship Club', 'kamal.admin@example.edu'),
 ('Cultural Society', 'lima.admin@example.edu'),
 ('Sports Club', 'lima.admin@example.edu')
) AS v(club_name, email)
JOIN clubs c ON c.club_name = v.club_name
JOIN users u ON u.email = v.email;

-- 6. Events (times are Bangladesh time, +06)
INSERT INTO events (club_id, venue_id, title, description, start_time, end_time, capacity, status)
SELECT c.club_id, ve.venue_id, v.title, v.description,
       v.start_time::timestamptz, v.end_time::timestamptz, v.capacity, v.status
FROM (VALUES
 ('Robotics Club', 'Computer Lab 2', 'Line Follower Workshop', 'Hands-on line follower robot building.', '2026-11-05 10:00:00+06', '2026-11-05 13:00:00+06', 40, 'completed'),
 ('Cultural Society', 'ECE Seminar Room', 'Poetry Evening', 'An evening of poetry and storytelling.', '2026-11-08 18:00:00+06', '2026-11-08 20:00:00+06', 50, 'completed'),
 ('Robotics Club', 'Computer Lab 2', 'Arduino Basics Bootcamp', 'Small group bootcamp. Only 3 seats.', '2026-12-02 10:00:00+06', '2026-12-02 14:00:00+06', 3, 'scheduled'),
 ('Sports Club', 'Central Field', 'Inter-Department Football', 'Football tournament between departments.', '2026-12-10 15:00:00+06', '2026-12-10 18:00:00+06', 200, 'scheduled'),
 ('Sports Club', 'Central Field', 'Cricket Tournament', 'Cancelled, same field and time as football.', '2026-12-10 15:00:00+06', '2026-12-10 18:00:00+06', 200, 'cancelled'),
 ('Entrepreneurship Club', 'ECE Seminar Room', 'Startup Pitch Day', 'Students pitch startup ideas.', '2026-12-15 14:00:00+06', '2026-12-15 17:00:00+06', 60, 'scheduled'),
 ('Cultural Society', 'University Auditorium', 'Winter Cultural Night', 'Music and dance performances.', '2026-12-20 17:00:00+06', '2026-12-20 21:00:00+06', 400, 'scheduled')
) AS v(club_name, venue_name, title, description, start_time, end_time, capacity, status)
JOIN clubs c ON c.club_name = v.club_name
JOIN venues ve ON ve.venue_name = v.venue_name;

-- 7. Club memberships
INSERT INTO club_memberships (club_id, student_id, status)
SELECT c.club_id, s.student_id, v.status
FROM (VALUES
 ('Robotics Club', 'rafi.ahmed@example.edu', 'active'),
 ('Robotics Club', 'tasnim.akter@example.edu', 'active'),
 ('Robotics Club', 'sabbir.hossain@example.edu', 'active'),
 ('Robotics Club', 'mahin.islam@example.edu', 'active'),
 ('Robotics Club', 'nabila.khan@example.edu', 'cancelled'),
 ('Cultural Society', 'nabila.khan@example.edu', 'active'),
 ('Cultural Society', 'sadia.rahman@example.edu', 'active'),
 ('Cultural Society', 'imran.hossain@example.edu', 'active'),
 ('Cultural Society', 'arif.chowdhury@example.edu', 'active'),
 ('Sports Club', 'sabbir.hossain@example.edu', 'active'),
 ('Sports Club', 'imran.hossain@example.edu', 'active'),
 ('Sports Club', 'arif.chowdhury@example.edu', 'active'),
 ('Sports Club', 'mahin.islam@example.edu', 'active'),
 ('Entrepreneurship Club', 'tasnim.akter@example.edu', 'active'),
 ('Entrepreneurship Club', 'sadia.rahman@example.edu', 'active'),
 ('Entrepreneurship Club', 'rafi.ahmed@example.edu', 'active')
) AS v(club_name, email, status)
JOIN clubs c ON c.club_name = v.club_name
JOIN users u ON u.email = v.email
JOIN students s ON s.user_id = u.user_id;

-- 8. Event registrations
INSERT INTO registrations (event_id, student_id, status)
SELECT e.event_id, s.student_id, v.status
FROM (VALUES
 ('Line Follower Workshop', 'rafi.ahmed@example.edu', 'attended'),
 ('Line Follower Workshop', 'tasnim.akter@example.edu', 'attended'),
 ('Line Follower Workshop', 'sabbir.hossain@example.edu', 'attended'),
 ('Line Follower Workshop', 'mahin.islam@example.edu', 'registered'),
 ('Line Follower Workshop', 'nabila.khan@example.edu', 'cancelled'),
 ('Poetry Evening', 'nabila.khan@example.edu', 'attended'),
 ('Poetry Evening', 'sadia.rahman@example.edu', 'attended'),
 ('Poetry Evening', 'imran.hossain@example.edu', 'attended'),
 ('Poetry Evening', 'arif.chowdhury@example.edu', 'cancelled'),
 ('Arduino Basics Bootcamp', 'rafi.ahmed@example.edu', 'registered'),
 ('Arduino Basics Bootcamp', 'tasnim.akter@example.edu', 'registered'),
 ('Arduino Basics Bootcamp', 'sabbir.hossain@example.edu', 'registered'),
 ('Arduino Basics Bootcamp', 'mahin.islam@example.edu', 'cancelled'),
 ('Inter-Department Football', 'sabbir.hossain@example.edu', 'registered'),
 ('Inter-Department Football', 'imran.hossain@example.edu', 'registered'),
 ('Inter-Department Football', 'arif.chowdhury@example.edu', 'registered'),
 ('Inter-Department Football', 'mahin.islam@example.edu', 'registered'),
 ('Winter Cultural Night', 'nabila.khan@example.edu', 'registered'),
 ('Winter Cultural Night', 'sadia.rahman@example.edu', 'registered'),
 ('Winter Cultural Night', 'imran.hossain@example.edu', 'registered'),
 ('Winter Cultural Night', 'arif.chowdhury@example.edu', 'registered'),
 ('Startup Pitch Day', 'tasnim.akter@example.edu', 'registered'),
 ('Startup Pitch Day', 'sadia.rahman@example.edu', 'registered'),
 ('Startup Pitch Day', 'rafi.ahmed@example.edu', 'registered')
) AS v(title, email, status)
JOIN events e ON e.title = v.title
JOIN users u ON u.email = v.email
JOIN students s ON s.user_id = u.user_id;

-- 9. Event expenses
INSERT INTO event_expenses (event_id, description, amount, expense_date)
SELECT e.event_id, v.description, v.amount, v.expense_date::date
FROM (VALUES
 ('Line Follower Workshop', 'Soldering kits', 4500.00, '2026-11-03'),
 ('Line Follower Workshop', 'Snacks and refreshments', 1800.50, '2026-11-05'),
 ('Poetry Evening', 'Sound system rental', 3000.00, '2026-11-07'),
 ('Poetry Evening', 'Printing posters', 650.00, '2026-11-06'),
 ('Arduino Basics Bootcamp', 'Arduino boards', 7500.00, '2026-11-12'),
 ('Inter-Department Football', 'Football kits', 5200.00, '2026-11-13'),
 ('Inter-Department Football', 'Referee fee', 1500.00, '2026-11-13'),
 ('Winter Cultural Night', 'Stage decoration', 12000.00, '2026-11-12'),
 ('Startup Pitch Day', 'Banner printing', 900.00, '2026-11-13')
) AS v(title, description, amount, expense_date)
JOIN events e ON e.title = v.title;

COMMIT;
