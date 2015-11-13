$(document).ready(function() {
    $("a.toggle_creq").click(function(){
        $("textarea.creq, input.creq, input.group, a.creq#checkall, a.creq#uncheckall").toggle();
        return false;
    });
    $("a.creq#checkall").click(function(){
        $("input.creq[type=checkbox], input.group[type=checkbox]").prop("checked", true);
        return false;
    });
    $("a.creq#uncheckall").click(function(){
        $("input.creq[type=checkbox], input.group[type=checkbox]").prop("checked", false);
        return false;
    });
    $("input.group[type=checkbox]").each(function(){ 
      $(this).change(function() {
        if($(this).prop("checked")){
          $(this).parent().parent().find("input.creq[type=checkbox][value$='" + $(this).prop("value") + "']").each(function(){
	    $(this).prop("checked", true);
          });
        } else {
          $(this).parent().parent().find("input.creq[type=checkbox][value$='" + $(this).prop("value") + "']").each(function(){
	    $(this).prop("checked", false);
          });
        }
      });
    });
 });
