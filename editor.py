import tkinter as tk
from tkinter import scrolledtext
import sys
import os

class Command:
    def __init__(self, doc, cursor_pos, selection, window_id):
        self.doc = doc
        self.cursor_before = cursor_pos
        self.selection_before = selection
        self.window_id = window_id
        self.cursor_after = None
        self.selection_after = None
    
    def execute(self):
        raise NotImplementedError
    
    def undo(self):
        raise NotImplementedError

class InsertCommand(Command):
    def __init__(self, doc, text, pos, cursor_pos, selection, window_id):
        super().__init__(doc, cursor_pos, selection, window_id)
        self.text = text
        self.pos = pos
    
    def execute(self):
        self.doc.content = self.doc.content[:self.pos] + self.text + self.doc.content[self.pos:]
        self.cursor_after = self.pos + len(self.text)
        self.selection_after = None
        return self.cursor_after, self.selection_after
    
    def undo(self):
        self.doc.content = self.doc.content[:self.pos] + self.doc.content[self.pos + len(self.text):]
        return self.cursor_before, self.selection_before

class DeleteCommand(Command):
    def __init__(self, doc, start, end, cursor_pos, selection, window_id):
        super().__init__(doc, cursor_pos, selection, window_id)
        self.start = start
        self.end = end
        self.deleted_text = doc.content[start:end]
    
    def execute(self):
        self.doc.content = self.doc.content[:self.start] + self.doc.content[self.end:]
        self.cursor_after = self.start
        self.selection_after = None
        return self.cursor_after, self.selection_after
    
    def undo(self):
        self.doc.content = self.doc.content[:self.start] + self.deleted_text + self.doc.content[self.start:]
        return self.cursor_before, self.selection_before

class Document:
    """Shared document model"""
    def __init__(self, filename):
        self.filename = filename
        self.content = ""
        self.undo_stack = []
        self.redo_stack = []
        self.windows = []
        self.last_command_type = None
        
        # Load file
        if os.path.exists(filename):
            with open(filename, 'r') as f:
                self.content = f.read().replace('\r\n', '\n')
    
    def save(self):
        with open(self.filename, 'w') as f:
            f.write(self.content)
    
    def execute_command(self, command):
        # Group consecutive similar commands
        if self.can_group_with_last(command):
            last_cmd = self.undo_stack[-1]
            if isinstance(command, InsertCommand) and isinstance(last_cmd, InsertCommand):
                if command.pos == last_cmd.pos + len(last_cmd.text):
                    last_cmd.text += command.text
                    cursor, selection = command.execute()
                    last_cmd.cursor_after = cursor
                    last_cmd.selection_after = selection
                    self.redo_stack.clear()
                    return cursor, selection
            elif isinstance(command, DeleteCommand) and isinstance(last_cmd, DeleteCommand):
                if command.end == last_cmd.start:  # Backspace
                    last_cmd.deleted_text = command.deleted_text + last_cmd.deleted_text
                    last_cmd.start = command.start
                    cursor, selection = command.execute()
                    last_cmd.cursor_after = cursor
                    last_cmd.selection_after = selection
                    self.redo_stack.clear()
                    return cursor, selection
                elif command.start == last_cmd.start:  # Delete key
                    last_cmd.deleted_text += command.deleted_text
                    last_cmd.end = command.end
                    cursor, selection = command.execute()
                    last_cmd.cursor_after = cursor
                    last_cmd.selection_after = selection
                    self.redo_stack.clear()
                    return cursor, selection
        
        cursor, selection = command.execute()
        self.undo_stack.append(command)
        self.redo_stack.clear()
        self.last_command_type = type(command)
        return cursor, selection
    
    def can_group_with_last(self, command):
        if not self.undo_stack:
            return False
        last_cmd = self.undo_stack[-1]
        if type(command) != type(last_cmd):
            return False
        if command.window_id != last_cmd.window_id:
            return False
        return True
    
    def undo(self, window_id):
        if not self.undo_stack:
            return None, None
        command = self.undo_stack.pop()
        cursor, selection = command.undo()
        self.redo_stack.append(command)
        return cursor, selection, command.window_id
    
    def redo(self, window_id):
        if not self.redo_stack:
            return None, None
        command = self.redo_stack.pop()
        cursor, selection = command.execute()
        self.undo_stack.append(command)
        return cursor, selection, command.window_id
    
    def register_window(self, window):
        self.windows.append(window)
    
    def unregister_window(self, window):
        if window in self.windows:
            self.windows.remove(window)
    
    def notify_windows(self, exclude_window=None):
        for window in self.windows:
            if window != exclude_window:
                window.refresh_display()

class EditorWindow(tk.Toplevel):
    def __init__(self, document, window_id, master=None):
        if master is None:
            super().__init__()
        else:
            super().__init__(master)
        
        self.document = document
        self.window_id = window_id
        self.cursor_pos = 0
        self.selection_start = None
        self.selection_end = None
        self.cursor_blink_state = True
        self.cursor_x_goal = None
        self.drag_start = None
        self.shift_drag_anchor = None
        
        self.title(f"Text Editor - {document.filename}")
        self.geometry("800x600")
        
        # Create text widget
        self.text_widget = tk.Text(self, wrap='word', font=('Monospace', 12),
                                   undo=False, autoseparators=False,
                                   insertwidth=2, insertbackground='black')
        self.text_widget.pack(fill='both', expand=True, side='left')
        
        # Create scrollbars
        self.v_scroll = tk.Scrollbar(self, orient='vertical', command=self.text_widget.yview)
        self.v_scroll.pack(side='right', fill='y')
        self.text_widget.config(yscrollcommand=self.v_scroll.set)
        
        self.h_scroll = tk.Scrollbar(self, orient='horizontal', command=self.text_widget.xview)
        self.h_scroll.pack(side='bottom', fill='x')
        self.text_widget.config(xscrollcommand=self.h_scroll.set)
        
        # Configure tags
        self.text_widget.tag_config('selection', background='lightblue')
        
        # Bind events
        self.text_widget.bind('<Button-1>', self.on_click)
        self.text_widget.bind('<B1-Motion>', self.on_drag)
        self.text_widget.bind('<Shift-Button-1>', self.on_shift_click)
        self.text_widget.bind('<Key>', self.on_key)
        self.text_widget.bind('<FocusIn>', self.on_focus_in)
        self.text_widget.bind('<FocusOut>', self.on_focus_out)
        self.text_widget.bind('<Control-s>', lambda e: self.save_file())
        self.text_widget.bind('<Control-c>', lambda e: self.copy())
        self.text_widget.bind('<Control-v>', lambda e: self.paste())
        self.text_widget.bind('<Control-z>', lambda e: self.undo())
        self.text_widget.bind('<Control-y>', lambda e: self.redo())
        self.text_widget.bind('<Control-o>', lambda e: self.open_new_window())
        
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        
        # Initial display
        self.refresh_display()
        self.text_widget.focus_set()
        
        # Start cursor blink
        self.blink_cursor()
    
    def get_index_from_position(self, x, y):
        """Convert screen coordinates to text index"""
        index = self.text_widget.index(f"@{x},{y}")
        row, col = map(int, index.split('.'))
        
        # Calculate absolute position
        pos = 0
        lines = self.document.content.split('\n')
        for i in range(row - 1):
            if i < len(lines):
                pos += len(lines[i]) + 1
        pos += min(col, len(lines[row - 1]) if row - 1 < len(lines) else 0)
        
        return pos
    
    def get_position_from_index(self, pos):
        """Convert text index to row, col"""
        lines = self.document.content.split('\n')
        current_pos = 0
        for row, line in enumerate(lines):
            if current_pos + len(line) >= pos:
                col = pos - current_pos
                return row + 1, col
            current_pos += len(line) + 1
        return len(lines), len(lines[-1]) if lines else 0
    
    def on_click(self, event):
        self.cursor_pos = self.get_index_from_position(event.x, event.y)
        self.selection_start = self.cursor_pos
        self.selection_end = None
        self.drag_start = self.cursor_pos
        self.shift_drag_anchor = self.cursor_pos
        self.cursor_x_goal = None
        self.refresh_display()
        return "break"
    
    def on_drag(self, event):
        if self.drag_start is not None:
            current_pos = self.get_index_from_position(event.x, event.y)
            self.cursor_pos = current_pos
            if current_pos != self.drag_start:
                self.selection_start = min(self.drag_start, current_pos)
                self.selection_end = max(self.drag_start, current_pos)
            else:
                self.selection_end = None
            self.refresh_display()
        return "break"
    
    def on_shift_click(self, event):
        if self.shift_drag_anchor is not None:
            current_pos = self.get_index_from_position(event.x, event.y)
            self.cursor_pos = current_pos
            self.selection_start = min(self.shift_drag_anchor, current_pos)
            self.selection_end = max(self.shift_drag_anchor, current_pos)
            self.refresh_display()
        return "break"
    
    def on_key(self, event):
        # Handle special keys
        if event.keysym in ('Left', 'Right', 'Up', 'Down'):
            self.handle_arrow_key(event.keysym)
            return "break"
        elif event.keysym == 'BackSpace':
            self.handle_backspace()
            return "break"
        elif event.keysym == 'Delete':
            self.handle_delete()
            return "break"
        elif event.keysym == 'Return':
            self.insert_text('\n')
            return "break"
        elif event.char and ord(event.char) >= 32:
            self.insert_text(event.char)
            return "break"
        
        return None
    
    def insert_text(self, text):
        if self.selection_end is not None:
            # Delete selection first
            start = min(self.selection_start, self.selection_end)
            end = max(self.selection_start, self.selection_end)
            cmd = DeleteCommand(self.document, start, end, self.cursor_pos,
                              (self.selection_start, self.selection_end), self.window_id)
            self.cursor_pos, _ = self.document.execute_command(cmd)
            self.selection_start = None
            self.selection_end = None
        
        cmd = InsertCommand(self.document, text, self.cursor_pos, self.cursor_pos,
                          (self.selection_start, self.selection_end), self.window_id)
        self.cursor_pos, _ = self.document.execute_command(cmd)
        self.selection_start = None
        self.selection_end = None
        self.cursor_x_goal = None
        
        self.refresh_display()
        self.ensure_cursor_visible()
        self.document.notify_windows(exclude_window=self)
    
    def handle_backspace(self):
        if self.selection_end is not None:
            start = min(self.selection_start, self.selection_end)
            end = max(self.selection_start, self.selection_end)
            cmd = DeleteCommand(self.document, start, end, self.cursor_pos,
                              (self.selection_start, self.selection_end), self.window_id)
            self.cursor_pos, _ = self.document.execute_command(cmd)
        elif self.cursor_pos > 0:
            cmd = DeleteCommand(self.document, self.cursor_pos - 1, self.cursor_pos,
                              self.cursor_pos, (self.selection_start, self.selection_end),
                              self.window_id)
            self.cursor_pos, _ = self.document.execute_command(cmd)
        
        self.selection_start = None
        self.selection_end = None
        self.cursor_x_goal = None
        self.refresh_display()
        self.ensure_cursor_visible()
        self.document.notify_windows(exclude_window=self)
    
    def handle_delete(self):
        if self.selection_end is not None:
            start = min(self.selection_start, self.selection_end)
            end = max(self.selection_start, self.selection_end)
            cmd = DeleteCommand(self.document, start, end, self.cursor_pos,
                              (self.selection_start, self.selection_end), self.window_id)
            self.cursor_pos, _ = self.document.execute_command(cmd)
        elif self.cursor_pos < len(self.document.content):
            cmd = DeleteCommand(self.document, self.cursor_pos, self.cursor_pos + 1,
                              self.cursor_pos, (self.selection_start, self.selection_end),
                              self.window_id)
            self.cursor_pos, _ = self.document.execute_command(cmd)
        
        self.selection_start = None
        self.selection_end = None
        self.cursor_x_goal = None
        self.refresh_display()
        self.ensure_cursor_visible()
        self.document.notify_windows(exclude_window=self)
    
    def handle_arrow_key(self, key):
        self.selection_start = None
        self.selection_end = None
        
        if key == 'Left':
            if self.cursor_pos > 0:
                self.cursor_pos -= 1
                if self.cursor_pos > 0 and self.document.content[self.cursor_pos] == '\n':
                    pass  # Already before newline
            self.cursor_x_goal = None
        elif key == 'Right':
            if self.cursor_pos < len(self.document.content):
                self.cursor_pos += 1
                if self.cursor_pos < len(self.document.content) and \
                   self.document.content[self.cursor_pos - 1] == '\n':
                    pass  # Already at start of next line
            self.cursor_x_goal = None
        elif key in ('Up', 'Down'):
            row, col = self.get_position_from_index(self.cursor_pos)
            if self.cursor_x_goal is None:
                self.cursor_x_goal = col
            
            if key == 'Up':
                row -= 1
            else:
                row += 1
            
            lines = self.document.content.split('\n')
            if 0 <= row - 1 < len(lines):
                col = min(self.cursor_x_goal, len(lines[row - 1]))
                pos = 0
                for i in range(row - 1):
                    pos += len(lines[i]) + 1
                pos += col
                self.cursor_pos = pos
        
        self.refresh_display()
        self.ensure_cursor_visible()
    
    def save_file(self):
        self.document.save()
    
    def copy(self):
        if self.selection_end is not None:
            start = min(self.selection_start, self.selection_end)
            end = max(self.selection_start, self.selection_end)
            text = self.document.content[start:end]
            self.clipboard_clear()
            self.clipboard_append(text)
    
    def paste(self):
        try:
            text = self.clipboard_get()
            self.insert_text(text)
        except:
            pass
    
    def undo(self):
        result = self.document.undo(self.window_id)
        if result[0] is not None:
            cursor, selection, window_id = result
            if window_id == self.window_id:
                self.cursor_pos = cursor
                self.selection_start, self.selection_end = selection if selection else (None, None)
            self.refresh_display()
            self.ensure_cursor_visible()
            self.document.notify_windows(exclude_window=self)
    
    def redo(self):
        result = self.document.redo(self.window_id)
        if result[0] is not None:
            cursor, selection, window_id = result
            if window_id == self.window_id:
                self.cursor_pos = cursor
                self.selection_start, self.selection_end = selection if selection else (None, None)
            self.refresh_display()
            self.ensure_cursor_visible()
            self.document.notify_windows(exclude_window=self)
    
    def open_new_window(self):
        new_window = EditorWindow(self.document, len(self.document.windows), master=self)
        self.document.register_window(new_window)
    
    def refresh_display(self):
        # Save scroll position
        y_pos = self.text_widget.yview()
        x_pos = self.text_widget.xview()
        
        # Update content
        self.text_widget.delete('1.0', 'end')
        self.text_widget.insert('1.0', self.document.content)
        
        # Restore scroll position
        self.text_widget.yview_moveto(y_pos[0])
        self.text_widget.xview_moveto(x_pos[0])
        
        # Update selection
        self.text_widget.tag_remove('selection', '1.0', 'end')
        if self.selection_end is not None:
            start_row, start_col = self.get_position_from_index(
                min(self.selection_start, self.selection_end))
            end_row, end_col = self.get_position_from_index(
                max(self.selection_start, self.selection_end))
            self.text_widget.tag_add('selection', f'{start_row}.{start_col}',
                                    f'{end_row}.{end_col}')
    
    def ensure_cursor_visible(self):
        row, col = self.get_position_from_index(self.cursor_pos)
        self.text_widget.see(f'{row}.{col}')
    
    def blink_cursor(self):
        if self.text_widget.focus_get() == self.text_widget:
            # Remove old cursor
            self.text_widget.tag_remove('cursor', '1.0', 'end')
            
            if self.cursor_blink_state and self.selection_end is None:
                # Draw cursor
                row, col = self.get_position_from_index(self.cursor_pos)
                self.text_widget.tag_add('cursor', f'{row}.{col}')
                self.text_widget.tag_config('cursor', background='black', foreground='white')
            
            self.cursor_blink_state = not self.cursor_blink_state
        
        self.after(500, self.blink_cursor)
    
    def on_focus_in(self, event):
        self.cursor_blink_state = True
    
    def on_focus_out(self, event):
        self.text_widget.tag_remove('cursor', '1.0', 'end')
    
    def on_close(self):
        self.document.unregister_window(self)
        if not self.document.windows:
            self.quit()
        else:
            self.destroy()

def main():
    if len(sys.argv) != 2:
        print("Usage: python3 editor.py <filename>")
        sys.exit(1)
    
    filename = sys.argv[1]
    
    # Create document
    document = Document(filename)
    
    # Create main window (use Tk for first window)
    root = tk.Tk()
    root.withdraw()  # Hide the default root
    
    # Create editor window
    window = EditorWindow(document, 0, master=root)
    document.register_window(window)
    
    root.mainloop()

if __name__ == '__main__':
    main()