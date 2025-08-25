# Admin Panel Documentation

This document provides an overview of the admin panel for the RunJPLib project.

## Accessing the Admin Panel

The admin panel is located at the `/admin` URL of the application (e.g., `http://localhost:5000/admin`).

Access is protected. You must provide an `ACCESS_CODE` to log in. This code is configured via the `ACCESS_CODE` environment variable.

Upon successful login, a JWT is stored in the browser's local storage, which is used to authenticate subsequent API requests.

## Features

The admin panel is a single-page application with several sections:

### 1. Dashboard

A welcome page.

### 2. Data Upload

This section is for migrating data from the local file system to the MongoDB database.

-   **University Data**:
    -   Select a `pdf_with_md*` folder from the dropdown list.
    -   Click "Start Upload" to begin the process.
    -   The tool will iterate through the subdirectories, extract metadata, read file contents (markdown, text, and PDF), and upload them to the `universities` collection in MongoDB.
    -   The operation uses `upsert`, meaning you can re-run the upload on the same folder to update existing entries or add new ones without creating duplicates.

-   **Blog Data**:
    -   Click "Start Upload" to upload all markdown files from the `/blogs` directory.
    -   The tool extracts metadata from the filenames and uploads the content to the `blogs` collection.
    -   This operation also uses `upsert`.

### 3. Data Management

This section allows for direct management of the data in MongoDB.

-   **University Data & Blog Data**:
    -   **Refresh List**: Fetches and displays a list of all items in the respective collection.
    -   **Clear All Data**: Deletes all documents in the collection. This is a destructive operation and requires confirmation.
    -   For each item, you can:
        -   **View**: Open the user-facing page for that item in a new tab.
        -   **Delete**: Remove the specific item from the database.

### 4. Data Generation

This section is a placeholder for future features related to content generation. It is not currently implemented.

## API Endpoints

The admin panel uses a set of API endpoints under `/admin/api/`. All endpoints are protected and require a valid JWT.

-   `POST /admin/api/login`: Authenticates with an access code and returns a JWT.
-   `GET /admin/api/university_folders`: Lists available `pdf_with_md*` folders.
-   `POST /admin/api/upload/university`: Starts the university data upload for a given folder.
-   `POST /admin/api/upload/blogs`: Starts the blog data upload.
-   `GET /admin/api/universities`: Lists universities from the database.
-   `DELETE /admin/api/universities/<id>`: Deletes a specific university.
-   `DELETE /admin/api/universities`: Clears the universities collection.
-   `GET /admin/api/blogs`: Lists blogs from the database.
-   `DELETE /admin/api/blogs/<id>`: Deletes a specific blog.
-   `DELETE /admin/api/blogs`: Clears the blogs collection.

## User-Facing View Integration

The following user-facing views have been modified to load data from MongoDB if it exists:

-   `/university/<name>/<deadline>`
-   `/blog/<title>`

If the requested data is found in MongoDB, it will be served from there. Otherwise, the application will fall back to the original file-based loading mechanism. This allows for a gradual migration and ensures that the site remains functional even for data that has not yet been uploaded to the database.

A new route, `/pdf/mongo/<item_id>`, has been added to serve PDF files directly from the binary data stored in MongoDB.
