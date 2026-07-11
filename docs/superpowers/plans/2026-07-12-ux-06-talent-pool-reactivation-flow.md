# UX-06 Talent Pool and Reactivation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build TAL-01 and TAL-02 so HR can organize reusable talent, search historical context, and create a new position application without overwriting prior applications.

**Architecture:** Add `TalentPoolViews.jsx` with shared talent-pool records, group list, searchable pool detail, member actions, and a reactivation drawer. `App.jsx` owns pool state and connects global navigation and candidate actions to the same talent-pool relationships; candidate application history remains the source of truth and receives a new linked application on successful reactivation.

**Tech Stack:** React 19, Vite 6, Lucide React, CSS, browser interaction QA.

## Global Constraints

- Reuse the current shell and the 24/18/16/14/13/12px typography scale.
- Talent-pool membership is independent of candidate application state.
- TAL-01 emphasizes groups, suitable roles, owners, activity, and retention rather than candidate cards.
- TAL-02 uses search and a comparison table with history and recent-contact context.
- Reactivation creates a new application and preserves every historical application.
- An active application for the same position blocks duplicate creation and links to the existing application.
- Positions outside the current user's permissions are not shown.
- “暂不适合”, “永久不再联系”, and “黑名单” remain distinct states; dangerous actions require explicit confirmation.
- Use synthetic candidates and masked contact data.

---

### Task 1: TAL-01 Talent Pool Groups

**Files:**
- Create: `docs/design/prototypes/ats-low-fi-option-2/src/TalentPoolViews.jsx`
- Modify: `docs/design/prototypes/ats-low-fi-option-2/src/App.jsx`
- Modify: `docs/design/prototypes/ats-low-fi-option-2/src/styles.css`

**Interfaces:**
- Consumes: `pools`, `members`, `onOpenPool(poolId)`, and `onCreatePool(pool)`.
- Produces: selected pool, group filters, visibility state, and group activity summaries.

- [x] **Step 1: Define pool and membership records**

Create public-team, restricted-position, and personal-follow-up pools with member count, suitable roles, owner, visibility, recent activity, default retention days, and member IDs.

- [x] **Step 2: Build group list and summary metrics**

Show total reusable talent, expiring retention, due follow-ups, and activations this month above a dense group list with name, purpose, roles, owner, visibility, members, retention, and activity.

- [x] **Step 3: Build create-pool flow**

Validate name, purpose, visibility, owner, and default retention; keep entered values after validation and add the new group without affecting candidate applications.

- [x] **Step 4: Add empty and permission states**

Distinguish no groups, no access, and no filter matches without exposing restricted pool names or members.

### Task 2: TAL-02 Pool Detail and Search

**Files:**
- Modify: `docs/design/prototypes/ats-low-fi-option-2/src/TalentPoolViews.jsx`
- Modify: `docs/design/prototypes/ats-low-fi-option-2/src/styles.css`

**Interfaces:**
- Consumes: selected pool, candidates, and pool memberships.
- Produces: filtered candidate IDs, updated tags/follow-up/retention, and selected member context.

- [x] **Step 1: Build searchable comparison table**

Support keyword, suitable-role, city, tag, owner, and follow-up filters. Show candidate, suitable roles, skills/tags, historical positions, latest conclusion, owner, next contact, retention, and primary action.

- [x] **Step 2: Build member detail context**

Expose masked contact, résumé summary, historical applications, pool reason, source, joined date, recent interaction, retention deadline, and audit activity.

- [x] **Step 3: Build membership maintenance**

Allow editing tags, suitable roles, owner, next contact date, and retention. Move/remove actions update membership only and never delete candidate history.

- [x] **Step 4: Add retention and dangerous-action states**

Show expiring/expired retention clearly. Require explicit confirmation for “永久不再联系” and “黑名单”, including impact copy and reason.

### Task 3: F-06 Reactivate Candidate

**Files:**
- Modify: `docs/design/prototypes/ats-low-fi-option-2/src/TalentPoolViews.jsx`
- Modify: `docs/design/prototypes/ats-low-fi-option-2/src/App.jsx`

**Interfaces:**
- Consumes: candidate, active authorized positions, résumé versions, and application history.
- Produces: a new linked application, activation event, updated pool activity, and candidate timeline entry.

- [x] **Step 1: Build reactivation drawer**

Show candidate context, target position, résumé version, source membership, owner, and a summary of the new application before creation.

- [x] **Step 2: Enforce position permissions and conflicts**

Only show recruiting positions in the user's authorized scope. Block an active same-position application and link to that existing application; warn but allow a historical terminal application.

- [x] **Step 3: Create linked application**

Append a new “新简历” application with source “人才库重新激活”, retain all historical applications, update the candidate timeline, and record the source pool/member relationship.

- [x] **Step 4: Verify activation completion state**

Keep the user on the member context, show the created position/application, and offer navigation to the candidate profile.

### Task 4: Candidate Entry Integration, QA, and Commit

**Files:**
- Modify: `docs/design/prototypes/ats-low-fi-option-2/src/App.jsx`
- Modify: `docs/design/prototypes/ats-low-fi-option-2/src/CandidateViews.jsx`
- Modify: `docs/design/prototypes/ats-low-fi-option-2/README.md`
- Modify: `docs/design/prototypes/ats-low-fi-option-2/design-qa.md`
- Create: TAL-01/TAL-02/reactivation desktop and mobile evidence images.

**Interfaces:**
- Consumes: candidate and talent-pool state from Tasks 1-3.
- Produces: one navigable UX-06 workflow with documented QA evidence.

- [x] **Step 1: Unify talent-pool entry points**

Route global talent-pool navigation, CAN-01 bulk action, CAN-02 action, and screening results into the same pool-membership flow.

- [x] **Step 2: Run the interaction matrix**

Test group filters, create validation, detail search, membership edits, retention state, move/remove, dangerous confirmation, allowed activation, duplicate conflict, and candidate-history preservation.

- [x] **Step 3: Run responsive and console QA**

Capture TAL-01, TAL-02, and reactivation at desktop 1280 and mobile 390; verify no body-level horizontal overflow and no console errors.

- [x] **Step 4: Build and commit**

Run `npm run build` and `git diff --check`, update QA evidence, and commit only UX-06 files.
