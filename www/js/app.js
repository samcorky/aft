// Fetch database status and update the UI
fetch('/api/test')
  .then(response => response.json())
  .then(data => {
    const statusDiv = document.getElementById('status');
    if(data.success) {
      statusDiv.className = "status success";
      statusDiv.innerText = "✓ Database connection successful! (" + data.boards_count + " boards)";
    } else {
      statusDiv.className = "status error";
      statusDiv.innerText = "✗ Database connection failed: " + data.message;
    }
  })
  .catch(err => {
    const statusDiv = document.getElementById('status');
    statusDiv.className = "status error";
    statusDiv.innerText = "✗ API error: " + err;
  });
