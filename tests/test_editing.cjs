const {test}=require("node:test"),assert=require("node:assert/strict");
const {validateExpenseEdit,validateParticipantEdit}=require("../static/editing.js");
test("valid expense edits normalize exactly in cents",()=>{
 assert.deepEqual(validateExpenseEdit("  Court rental ","12.5","venue"),{
  title:"Court rental",amount:"12.50",category:"venue"
 });
 assert.deepEqual(validateExpenseEdit("Snacks","0.01","food"),{
  title:"Snacks",amount:"0.01",category:"food"
 });
});
test("invalid expense edits fail closed",()=>{
 for(const value of ["0","-2","1e5","1.234","NaN","100000.01","1,000"]){
  assert.throws(()=>validateExpenseEdit("Court",value,"venue"));
 }
 assert.throws(()=>validateExpenseEdit(" ","15","food"),/name/);
 assert.throws(()=>validateExpenseEdit("Court","15","unknown"),/category/);
});
test("participant weight validation uses strict whole numbers",()=>{
 assert.deepEqual(validateParticipantEdit("  Alex  ","3"),{name:"Alex",weight:3});
 for(const weight of ["0","11","1.5","2.2","x","1e1"]){
  assert.throws(()=>validateParticipantEdit("Alex",weight));
 }
 assert.throws(()=>validateParticipantEdit(" ",1),/name/);
});
