# academic-radar
# Primary School Early Warning System

An offline-first, lightweight tracking system designed to detect when primary school students are falling behind academically *before* final exams, using continuous assessment test (CAT) data.

## The Problem
Schools often rely on physical exercise books. By the time a teacher manually identifies a downward trend in a student's performance, it is often too late to intervene effectively before national exams.

## Architecture
The system is decoupled into four core layers, designed to run locally on school hardware without requiring constant internet access:

1. **Data Ingestion:** An offline-capable UI for teachers to input chronological CAT scores. Includes strict validation to prevent impossible scores.
2. **Storage:** A local SQLite database storing student profiles, subject data, and test scores.
3. **Trend Analyzer (Logic Engine):** A Python-based evaluation engine that calculates rolling averages and flags negative velocity in a student's performance compared to their own historical baseline.
4. **Dashboard:** A UI that ranks students by **risk of falling behind** (Red/Yellow/Green) rather than by highest overall marks.

## Handling Edge Cases
- **Offline First:** Built to run locally via FastAPI/SQLite or as a PWA, bypassing rural internet constraints.
- **Missing Data:** The analyzer uses temporal logic. Missed exams are flagged as `Excused`, preserving the student's baseline average without registering as a `0`.
- **Mid-Term Joiners:** The system requires a minimum data threshold (e.g., 3 assignments) before calculating trends, outputting "Insufficient Data" until the threshold is met.

## Build Order
1. **Database Schema:** Define data structures.
2. **Ingestion Layer:** Build data capture and validation.
3. **Trend Analyzer:** Implement the mathematical tracking logic.
4. **Dashboard:** Surface the insights visually.
