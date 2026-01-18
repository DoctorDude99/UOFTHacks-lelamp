// Habit mapping - connects display names to backend variable names
const habitMapping = {
'Drink Water': 'bottle',
'Eating Bananas': 'banana',
'Brushing Teeth': 'toothbrush',
'Watering your Plant': 'pottedplant',
'Walk your Dog': 'dog'
};

// Habit submission
const submitBtn = document.getElementById('submitHabit');
const habitsInput = document.getElementById('habits');
const dailyTargetInput = document.getElementById('daily-frequency');
const habitsListBox = document.getElementById('habitsListBox');
const habitsTableBody = document.getElementById('habitsTableBody');
const habits = [];

submitBtn.addEventListener('click', function() {
const habitName = habitsInput.value;
const dailyTarget = dailyTargetInput.value || 1;

if (habitName) {
    // Create habit object with backend variable name
    const habitData = {
    displayName: habitName,
    variableName: habitMapping[habitName],
    dailyTarget: parseInt(dailyTarget),
    streak: 0
    };
    
    habits.push(habitData);
    habitsListBox.classList.add('visible');
    
    // Send to backend
    sendHabitToBackend(habitData);
    
    const row = document.createElement('tr');
    
    // Habit name cell
    const cell = document.createElement('td');
    cell.textContent = habitName;
    row.appendChild(cell);
    
    // Daily streak cell (starts at 0)
    const streakCell = document.createElement('td');
    streakCell.textContent = '0';
    row.appendChild(streakCell);
    
    // Delete button cell
    const deleteCell = document.createElement('td');
    const deleteBtn = document.createElement('button');
    deleteBtn.className = 'delete-btn';
    deleteBtn.innerHTML = '<svg viewBox="0 0 24 24"><line x1="5" y1="12" x2="19" y2="12"></line></svg>';
    deleteBtn.addEventListener('click', function() {
    const index = habits.findIndex(h => h.displayName === habitName);
    if (index > -1) {
        deleteHabitFromBackend(habitData.variableName);
        habits.splice(index, 1);
    }
    row.remove();
    if (habits.length === 0) {
        habitsListBox.classList.remove('visible');
    }
    });
    deleteCell.appendChild(deleteBtn);
    row.appendChild(deleteCell);
    
    habitsTableBody.appendChild(row);
    habitsInput.selectedIndex = 0;
    dailyTargetInput.value = '';
}
});

// Function to send habit to Flask backend
async function sendHabitToBackend(habitData) {
try {
    const response = await fetch('http://localhost:5000/api/habits', {
    method: 'POST',
    headers: {
        'Content-Type': 'application/json',
    },
    body: JSON.stringify(habitData)
    });
    const result = await response.json();
    console.log('Habit created:', result);
} catch (error) {
    console.error('Error creating habit:', error);
}
}

// Function to delete habit from backend
async function deleteHabitFromBackend(variableName) {
try {
    const response = await fetch(`http://localhost:5000/api/habits/${variableName}`, {
    method: 'DELETE'
    });
    const result = await response.json();
    console.log('Habit deleted:', result);
} catch (error) {
    console.error('Error deleting habit:', error);
}
}

// Allow Enter key to submit
habitsInput.addEventListener('keypress', function(e) {
if (e.key === 'Enter') {
    submitBtn.click();
}
});

// Allow change event to submit
habitsInput.addEventListener('change', function() {
if (habitsInput.value) {
    // Optionally auto-submit on selection
}
});

// Lamp toggle for dark mode
const lamp = document.querySelector('.lamp-decoration');
const body = document.body;

lamp.addEventListener('click', function() {
body.classList.toggle('dark-mode');
});

// Image preview functionality
const fileInput = document.getElementById('fileInput');
const imagePreview = document.getElementById('imagePreview');

fileInput.addEventListener('change', function(e) {
const file = e.target.files[0];
if (file) {
    const reader = new FileReader();
    reader.onload = function(e) {
    imagePreview.src = e.target.result;
    imagePreview.style.display = 'block';
    }
    reader.readAsDataURL(file);
}
});